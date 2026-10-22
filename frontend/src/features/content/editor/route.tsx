"use client";

import { useParams } from "next/navigation";

import { ContentEditor } from "./content-editor";

export function ContentEditorRoute() {
  const { itemId } = useParams<{ itemId: string }>();
  // Keyed so switching items resets all editor state.
  return <ContentEditor key={itemId} itemId={itemId} />;
}
