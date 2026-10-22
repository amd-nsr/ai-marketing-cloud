from django.dispatch import Signal

#: Sent after a new organization and its owner membership are created.
#: Other domain apps connect to it to create their per-organization defaults.
#: kwargs: organization, owner
organization_created = Signal()
