"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  PageLoader,
  SettingsLayouts,
  ContentAction,
  toast,
} from "@opal/layouts";
import { ErrorCallout } from "@/components/ErrorCallout";
import { Section } from "@/layouts/general-layouts";
import Text from "@/refresh-components/texts/Text";
import Card from "@/refresh-components/cards/Card";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button, CopyButton, EmptyMessageCard, Modal } from "@opal/components";
import { SvgKey, SvgPlusCircle } from "@opal/icons";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { ConfirmEntityModal } from "@/sections/modals/ConfirmEntityModal";
import {
  createApiKey,
  deleteApiKey,
  regenerateApiKey,
} from "@/app/admin/service-accounts/lib";
import {
  ApiKeyDescriptor,
  ApiKeyRole,
} from "@/app/admin/service-accounts/types";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

const route = ADMIN_ROUTES.SERVICE_ACCOUNTS_CE;

const ROLE_DESCRIPTIONS: Record<ApiKeyRole, string> = {
  limited: "Chat only — for bots and app integrations",
  basic: "Same access as a regular user",
  admin: "Full admin API access",
};

function ServiceAccountsContent() {
  const {
    data: keys,
    isLoading,
    error,
    mutate,
  } = useSWR<ApiKeyDescriptor[]>("/api/admin/api-key", errorHandlingFetcher);

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState<ApiKeyRole>("limited");
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ApiKeyDescriptor | null>(
    null
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleCreate = async () => {
    setIsSubmitting(true);
    try {
      const created = await createApiKey(newName.trim(), newRole);
      setShowCreate(false);
      setNewName("");
      setRevealedKey(created.api_key ?? null);
      mutate();
      toast.success("Service account created");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegenerate = async (key: ApiKeyDescriptor) => {
    try {
      const regenerated = await regenerateApiKey(key.api_key_id);
      setRevealedKey(regenerated.api_key ?? null);
      mutate();
      toast.success("Key regenerated — the old key no longer works");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to regenerate");
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setIsSubmitting(true);
    try {
      await deleteApiKey(deleteTarget.api_key_id);
      mutate();
      toast.success("Service account deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete");
    } finally {
      setIsSubmitting(false);
      setDeleteTarget(null);
    }
  };

  if (isLoading) {
    return <PageLoader />;
  }

  if (error || !keys) {
    return (
      <ErrorCallout
        errorTitle="Failed to load service accounts"
        errorMsg={error?.info?.detail || "An unknown error occurred"}
      />
    );
  }

  return (
    <>
      {/* One-time key reveal */}
      <Modal open={!!revealedKey}>
        <Modal.Content width="sm">
          <Modal.Header
            title="API Key"
            icon={SvgKey}
            onClose={() => setRevealedKey(null)}
            description="This key is only shown once — copy it now."
          />
          <Modal.Body>
            <Card variant="secondary">
              <Section
                flexDirection="row"
                justifyContent="between"
                alignItems="center"
              >
                <Text text03 secondaryMono className="break-all">
                  {revealedKey}
                </Text>
                <CopyButton getCopyText={() => revealedKey ?? ""} />
              </Section>
            </Card>
          </Modal.Body>
        </Modal.Content>
      </Modal>

      {/* Create modal */}
      <Modal open={showCreate}>
        <Modal.Content width="sm">
          <Modal.Header
            title="New Service Account"
            icon={SvgKey}
            onClose={() => setShowCreate(false)}
            description="Creates a headless account with its own API key."
          />
          <Modal.Body>
            <Section flexDirection="column" alignItems="start" gap={3}>
              <InputTypeIn
                placeholder="Name (e.g. n8n-bot)"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
              <InputSelect
                value={newRole}
                onValueChange={(value: string) =>
                  setNewRole(value as ApiKeyRole)
                }
              >
                <InputSelect.Trigger placeholder="Role" />
                <InputSelect.Content>
                  {(Object.keys(ROLE_DESCRIPTIONS) as ApiKeyRole[]).map(
                    (role) => (
                      <InputSelect.Item key={role} value={role}>
                        {role} — {ROLE_DESCRIPTIONS[role]}
                      </InputSelect.Item>
                    )
                  )}
                </InputSelect.Content>
              </InputSelect>
              <Button
                disabled={isSubmitting || !newName.trim()}
                onClick={handleCreate}
              >
                {isSubmitting ? "Creating..." : "Create"}
              </Button>
            </Section>
          </Modal.Body>
        </Modal.Content>
      </Modal>

      {deleteTarget && (
        <ConfirmEntityModal
          danger
          entityType="service account"
          entityName={deleteTarget.api_key_name || deleteTarget.api_key_display}
          onClose={() => setDeleteTarget(null)}
          onSubmit={handleDelete}
          additionalDetails="Anything using this key will stop working immediately."
        />
      )}

      <Card variant="primary">
        <ContentAction
          title="Service Accounts"
          description="Headless accounts with API keys, for bots and integrations. The Telegram/LINE/Discord bots manage their own keys automatically."
          sizePreset="main-content"
          variant="section"
          rightChildren={
            <Button
              icon={SvgPlusCircle}
              prominence="secondary"
              onClick={() => setShowCreate(true)}
            >
              New Service Account
            </Button>
          }
        />

        {keys.length === 0 ? (
          <EmptyMessageCard
            sizePreset="main-ui"
            title="No service accounts"
            description="Create one to call the Onyx API from other systems."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="[&>th]:whitespace-nowrap">
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Key</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((key) => (
                <TableRow key={key.api_key_id}>
                  <TableCell>
                    <Text text04 mainUiBody>
                      {key.api_key_name || "Unnamed"}
                    </Text>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{key.api_key_role}</Badge>
                  </TableCell>
                  <TableCell>
                    <Text text03 secondaryMono>
                      {key.api_key_display}
                    </Text>
                  </TableCell>
                  <TableCell>
                    <Section
                      flexDirection="row"
                      justifyContent="start"
                      gap={2}
                      width="fit"
                    >
                      <Button
                        prominence="secondary"
                        size="sm"
                        onClick={() => handleRegenerate(key)}
                      >
                        Regenerate
                      </Button>
                      <Button
                        variant="danger"
                        prominence="secondary"
                        size="sm"
                        onClick={() => setDeleteTarget(key)}
                      >
                        Delete
                      </Button>
                    </Section>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </>
  );
}

export default function Page() {
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={route.title}
        description="API keys for connecting bots and external systems to Onyx."
      />
      <SettingsLayouts.Body>
        <ServiceAccountsContent />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
