export type ArtifactVisibility = "private" | "public_org" | "public";

export interface ArtifactPublication {
  id: string;
  artifact_id: string;
  version: number;
  visibility: Exclude<ArtifactVisibility, "private">;
  url: string;
  content_hash: string;
  created_at: string;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail ?? "Artifact request failed");
  }
  // SAFETY: Each caller supplies the response type for its matching API route.
  return response.json() as Promise<T>;
}

export async function fetchLatestArtifactPublication(
  artifactId: string
): Promise<ArtifactPublication | null> {
  const response = await fetch(
    `/api/artifacts/${artifactId}/publications/latest`
  );
  return parseResponse<ArtifactPublication | null>(response);
}

export async function publishArtifact(
  artifactId: string,
  visibility: Exclude<ArtifactVisibility, "private">,
  revisionId?: string
): Promise<ArtifactPublication> {
  const response = await fetch(`/api/artifacts/${artifactId}/publications`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visibility, revision_id: revisionId }),
  });
  return parseResponse<ArtifactPublication>(response);
}

export async function revokeArtifactPublication(
  artifactId: string,
  publicationId: string
): Promise<void> {
  const response = await fetch(
    `/api/artifacts/${artifactId}/publications/${publicationId}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new Error("Could not revoke the artifact link");
  }
}

export async function revokeAllArtifactPublications(
  artifactId: string
): Promise<void> {
  const response = await fetch(`/api/artifacts/${artifactId}/publications`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error("Could not revoke the artifact links");
  }
}
