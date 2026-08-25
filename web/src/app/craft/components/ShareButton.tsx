"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Button, Popover, Text } from "@opal/components";
import {
  SvgLink,
  SvgCopy,
  SvgCheck,
  SvgX,
  SvgGlobe,
  SvgRefreshCw,
} from "@opal/icons";
import {
  fetchLatestArtifactPublication,
  publishArtifact,
  revokeArtifactPublication,
  setSessionSharing,
} from "@/app/craft/services/apiServices";
import type { SharingScope } from "@/app/craft/types/streamingTypes";
import { cn } from "@opal/utils";
import { Section } from "@/layouts/general-layouts";
import { ContentAction, toast } from "@opal/layouts";
import { SWR_KEYS } from "@/lib/swr-keys";

interface ShareButtonProps {
  sessionId: string;
  webappUrl: string;
  sharingScope: SharingScope;
  onScopeChange?: () => void;
}

const SCOPE_OPTIONS: {
  value: SharingScope;
  label: string;
  description: string;
}[] = [
  {
    value: "private",
    label: "Private",
    description: "Only you can view this app.",
  },
  {
    value: "public_org",
    label: "Organization",
    description: "Anyone logged into your Onyx can view this app.",
  },
  {
    value: "public",
    label: "Anyone with the link",
    description: "No Onyx account is required.",
  },
];

export default function ShareButton({
  sessionId,
  webappUrl,
  sharingScope: initialScope,
  onScopeChange,
}: ShareButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [sharingScope, setSharingScope] = useState<SharingScope>(initialScope);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">(
    "idle"
  );
  const [isLoading, setIsLoading] = useState(false);
  const { data: publication, mutate: mutatePublication } = useSWR(
    SWR_KEYS.buildSessionArtifactPublication(sessionId),
    () => fetchLatestArtifactPublication(sessionId),
    { revalidateOnFocus: false }
  );

  useEffect(() => {
    if (publication) setSharingScope(publication.visibility);
  }, [publication]);

  const isShared = sharingScope !== "private";

  const shareUrl =
    typeof window !== "undefined"
      ? publication?.url ||
        (webappUrl.startsWith("http")
          ? webappUrl
          : `${window.location.origin}${webappUrl}`)
      : publication?.url || webappUrl;

  const handlePublish = async () => {
    const nextPublication = await publishArtifact(sessionId);
    await mutatePublication(nextPublication, { revalidate: false });
    setSharingScope("public");
    onScopeChange?.();
    toast.success(`Published version ${nextPublication.version}`);
  };

  const handleSelect = async (scope: SharingScope) => {
    if (scope === sharingScope || isLoading) return;
    setIsLoading(true);
    try {
      if (scope === "public") {
        await handlePublish();
      } else {
        if (publication) {
          await revokeArtifactPublication(sessionId, publication.id);
          await mutatePublication(null, { revalidate: false });
        }
        await setSessionSharing(sessionId, scope);
        onScopeChange?.();
      }
      setSharingScope(scope);
    } catch (err) {
      console.error("Failed to update sharing:", err);
      toast.error(
        scope === "public"
          ? "Failed to publish app"
          : "Failed to update sharing"
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = async () => {
    let success = false;
    try {
      await navigator.clipboard.writeText(shareUrl);
      success = true;
    } catch {
      try {
        const el = document.createElement("textarea");
        el.value = shareUrl;
        el.style.cssText = "position:fixed;opacity:0";
        document.body.appendChild(el);
        el.focus();
        el.select();
        success = document.execCommand("copy");
        document.body.removeChild(el);
      } catch {}
    }
    setCopyState(success ? "copied" : "error");
    setTimeout(() => setCopyState("idle"), 2000);
  };

  return (
    <Section width="fit" height="fit">
      <Popover open={isOpen} onOpenChange={setIsOpen}>
        <Popover.Trigger asChild>
          <Button
            variant="action"
            prominence={isShared ? "primary" : "tertiary"}
            icon={sharingScope === "public" ? SvgGlobe : SvgLink}
            aria-label="Share webapp"
          >
            {isShared ? "Shared" : "Share"}
          </Button>
        </Popover.Trigger>
        <Popover.Content side="bottom" align="end" width="lg" sideOffset={4}>
          <Section
            alignItems="stretch"
            gap={1}
            padding={1}
            width="full"
            height="fit"
          >
            {/* Scope options */}
            <Section alignItems="stretch" gap={1} width="full">
              {SCOPE_OPTIONS.map((opt) => (
                <div
                  key={opt.value}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleSelect(opt.value)}
                  onKeyDown={(e) =>
                    e.key === "Enter" && handleSelect(opt.value)
                  }
                  aria-disabled={isLoading}
                  className={cn(
                    "cursor-pointer rounded-08 transition-colors",
                    sharingScope === opt.value
                      ? "bg-background-tint-03"
                      : "hover:bg-background-tint-02"
                  )}
                >
                  <ContentAction
                    title={opt.label}
                    description={opt.description}
                    sizePreset="main-ui"
                    variant="section"
                    padding={1}
                  />
                </div>
              ))}
            </Section>

            {/* Copy link — shown when not private */}
            {isShared && (
              <div className="flex flex-col rounded-08 bg-background-tint-02">
                <Section
                  flexDirection="row"
                  alignItems="center"
                  gap={1}
                  padding={1}
                  width="full"
                  height="fit"
                >
                  <div className="min-w-0 flex-1 overflow-hidden">
                    <Text font="secondary-body" color="text-03" maxLines={1}>
                      {shareUrl}
                    </Text>
                  </div>
                  <Button
                    variant="action"
                    prominence="tertiary"
                    size="md"
                    icon={
                      copyState === "copied"
                        ? SvgCheck
                        : copyState === "error"
                          ? SvgX
                          : SvgCopy
                    }
                    onClick={handleCopy}
                    aria-label="Copy link"
                  />
                </Section>
                {sharingScope === "public" && publication && (
                  <Section padding={1} width="full" height="fit">
                    <Button
                      width="full"
                      variant="action"
                      prominence="secondary"
                      icon={SvgRefreshCw}
                      disabled={isLoading}
                      onClick={async () => {
                        setIsLoading(true);
                        try {
                          await handlePublish();
                        } catch (err) {
                          console.error("Failed to publish artifact:", err);
                          toast.error("Failed to publish latest version");
                        } finally {
                          setIsLoading(false);
                        }
                      }}
                    >
                      Publish latest version
                    </Button>
                  </Section>
                )}
              </div>
            )}
          </Section>
        </Popover.Content>
      </Popover>
    </Section>
  );
}
