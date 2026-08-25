"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, Popover, Text } from "@opal/components";
import {
  SvgCheck,
  SvgCode,
  SvgCopy,
  SvgExternalLink,
  SvgGlobe,
  SvgLink,
  SvgLoader,
  SvgRefreshCw,
} from "@opal/icons";
import { toast } from "@opal/layouts";

import {
  ArtifactToolFinal,
  ArtifactToolPacket,
  PacketType,
} from "@/app/app/services/streamingModels";
import {
  ArtifactPublication,
  ArtifactVisibility,
  fetchLatestArtifactPublication,
  publishArtifact,
  revokeAllArtifactPublications,
} from "@/app/app/services/artifactServices";
import { MessageRenderer } from "../interfaces";

const SHARE_OPTIONS: Array<{
  value: ArtifactVisibility;
  label: string;
  description: string;
}> = [
  {
    value: "private",
    label: "Private",
    description: "Only you can open this artifact.",
  },
  {
    value: "public_org",
    label: "Organization",
    description: "Anyone signed in to this Onyx workspace.",
  },
  {
    value: "public",
    label: "Anyone with the link",
    description: "No Onyx account is required.",
  },
];

function ArtifactShare({ artifact }: { artifact: ArtifactToolFinal }) {
  const [publication, setPublication] = useState<ArtifactPublication | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    fetchLatestArtifactPublication(artifact.artifact_id)
      .then((value) => active && setPublication(value))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [artifact.artifact_id]);

  const visibility: ArtifactVisibility = publication?.visibility ?? "private";

  const selectVisibility = async (
    next: ArtifactVisibility,
    publishLatest = false
  ) => {
    if (loading || (next === visibility && !publishLatest)) return;
    setLoading(true);
    try {
      if (next === "private") {
        if (publication) {
          await revokeAllArtifactPublications(artifact.artifact_id);
        }
        setPublication(null);
        toast.success("Artifact is private");
      } else {
        if (publication && next !== visibility) {
          await revokeAllArtifactPublications(artifact.artifact_id);
        }
        const nextPublication = await publishArtifact(
          artifact.artifact_id,
          next,
          publishLatest ? undefined : artifact.revision_id
        );
        setPublication(nextPublication);
        toast.success(`Published version ${nextPublication.version}`);
      }
    } catch (error) {
      console.error("Failed to share artifact", error);
      toast.error("Could not update artifact sharing");
    } finally {
      setLoading(false);
    }
  };

  const copyLink = async () => {
    if (!publication) return;
    try {
      await navigator.clipboard.writeText(publication.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Could not copy the link");
    }
  };

  return (
    <Popover>
      <Popover.Trigger asChild>
        <Button
          variant="action"
          prominence={publication ? "secondary" : "tertiary"}
          size="sm"
          icon={publication?.visibility === "public" ? SvgGlobe : SvgLink}
          aria-label="Share artifact"
        >
          {publication ? "Shared" : "Share"}
        </Button>
      </Popover.Trigger>
      <Popover.Content side="bottom" align="end" width="lg" sideOffset={6}>
        <div className="flex w-full flex-col gap-1 p-1">
          <div className="px-2 pb-1 pt-2">
            <Text font="main-ui-action" color="text-02">
              Share artifact
            </Text>
            <Text font="secondary-body" color="text-03">
              Links always open this published version.
            </Text>
          </div>
          {SHARE_OPTIONS.map((option) => (
            <button
              type="button"
              key={option.value}
              disabled={loading}
              onClick={() => selectVisibility(option.value)}
              className="flex w-full items-start justify-between gap-3 rounded-08 px-2 py-2 text-left transition-colors hover:bg-background-tint-02 disabled:opacity-50"
            >
              <span className="flex min-w-0 flex-col">
                <Text font="main-ui-body" color="text-02">
                  {option.label}
                </Text>
                <Text font="secondary-body" color="text-03">
                  {option.description}
                </Text>
              </span>
              {visibility === option.value && (
                <SvgCheck className="mt-1 size-4 shrink-0 stroke-text-02" />
              )}
            </button>
          ))}
          {publication && (
            <div className="mt-1 flex items-center gap-1 border-t border-border-01 px-1 pt-2">
              <Button
                variant="action"
                prominence="tertiary"
                size="sm"
                icon={copied ? SvgCheck : SvgCopy}
                onClick={copyLink}
                width="full"
              >
                {copied ? "Copied" : "Copy link"}
              </Button>
              <Button
                variant="action"
                prominence="tertiary"
                size="sm"
                icon={SvgRefreshCw}
                onClick={() => selectVisibility(publication.visibility, true)}
                aria-label="Publish latest artifact version"
              />
            </div>
          )}
        </div>
      </Popover.Content>
    </Popover>
  );
}

function ArtifactCard({ artifact }: { artifact: ArtifactToolFinal }) {
  return (
    <section
      data-testid="chat-artifact-card"
      className="group/artifact my-2 overflow-hidden rounded-16 border border-border-01 bg-background-neutral-00 shadow-sm"
    >
      <header className="flex min-h-14 items-center justify-between gap-3 border-b border-border-01 bg-background-tint-01 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="grid size-8 shrink-0 place-items-center rounded-08 border border-border-01 bg-background-neutral-00 shadow-xs">
            <SvgCode className="size-4 stroke-text-02" />
          </div>
          <div className="min-w-0">
            <Text font="main-ui-action" color="text-01" maxLines={1}>
              {artifact.title}
            </Text>
            <div className="flex items-center gap-1.5">
              <span className="size-1.5 rounded-full bg-status-success-05" />
              <Text font="secondary-body" color="text-03">
                {`HTML · Version ${artifact.version}`}
              </Text>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <ArtifactShare artifact={artifact} />
          <Button
            variant="action"
            prominence="tertiary"
            size="sm"
            icon={SvgExternalLink}
            onClick={() =>
              window.open(artifact.preview_url, "_blank", "noopener,noreferrer")
            }
            aria-label="Open artifact in a new tab"
          >
            Open
          </Button>
        </div>
      </header>
      <div className="relative h-[360px] bg-background-dark-00">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-[0.035] [background-image:linear-gradient(to_right,currentColor_1px,transparent_1px),linear-gradient(to_bottom,currentColor_1px,transparent_1px)] [background-size:24px_24px]"
        />
        <iframe
          title={artifact.title}
          src={artifact.preview_url}
          sandbox="allow-scripts allow-modals allow-downloads"
          className="relative h-full w-full border-0 bg-white"
        />
      </div>
    </section>
  );
}

export const ArtifactToolRenderer: MessageRenderer<ArtifactToolPacket, {}> = ({
  packets,
  onComplete,
  children,
}) => {
  const artifact = useMemo(
    () =>
      // SAFETY: The discriminated packet type narrows this object to ArtifactToolFinal.
      packets.find(
        (packet) => packet.obj.type === PacketType.ARTIFACT_TOOL_FINAL
      )?.obj as ArtifactToolFinal | undefined,
    [packets]
  );

  useEffect(() => {
    if (artifact) onComplete();
  }, [artifact, onComplete]);

  if (!artifact) {
    return children([
      {
        icon: SvgLoader,
        status: "Building artifact",
        supportsCollapsible: false,
        content: (
          <div className="my-2 flex h-28 items-center justify-center rounded-16 border border-border-01 bg-background-tint-01">
            <div className="flex items-center gap-2 text-text-03">
              <SvgLoader className="size-4 animate-spin" />
              <Text font="main-ui-body" color="text-03">
                Building interactive artifact…
              </Text>
            </div>
          </div>
        ),
      },
    ]);
  }

  return children([
    {
      icon: SvgCode,
      status: `Created ${artifact.title}`,
      supportsCollapsible: false,
      content: <ArtifactCard artifact={artifact} />,
    },
  ]);
};
