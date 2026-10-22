"""Run the marketing-plan evaluation cases against the configured AI provider.

    uv run python manage.py eval_marketing_plans [--case restaurant-cafe] [--out report.json]

With a real provider this makes one billed request per case. Nothing is persisted.
"""

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from apps.marketing.evals.runner import load_cases, run_case


class Command(BaseCommand):
    help = "Evaluate marketing plan generation across representative industries."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--case", action="append", help="Run only these case IDs.")
        parser.add_argument("--out", help="Write full results (including plans) to this JSON file.")

    def handle(self, *args: Any, **options: Any) -> None:
        cases = [c for c in load_cases() if not options["case"] or c["id"] in options["case"]]
        results = [run_case(c) for c in cases]
        for r in results:
            mark = self.style.SUCCESS("PASS") if r.passed else self.style.ERROR("FAIL")
            failed = [k for k, v in r.checks.items() if not v]
            self.stdout.write(f"{mark} {r.case_id} [{r.provider}/{r.model}] {', '.join(failed)}")
            for note in r.notes:
                self.stdout.write(f"     - {note}")
        passed = sum(r.passed for r in results)
        self.stdout.write(f"\n{passed}/{len(results)} cases passed automated checks.")
        if results and results[0].provider == "mock":
            self.stdout.write(
                self.style.WARNING("Provider is MOCK: this exercises the pipeline, not AI quality.")
            )
        if options["out"]:
            Path(options["out"]).write_text(
                json.dumps([r.__dict__ for r in results], indent=2, default=str)
            )
