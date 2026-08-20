"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PageLoader, SettingsLayouts, ContentAction } from "@opal/layouts";
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
import { Button, EmptyMessageCard } from "@opal/components";
import SvgSimpleLoader from "@opal/icons/simple-loader";
import { errorHandlingFetcher } from "@/lib/fetcher";
import {
  chatHistoryUrl,
  exportUrl,
  formatCost,
  formatTokens,
  overviewUrl,
  sessionMessagesUrl,
} from "@/app/admin/usage-report/lib";
import {
  ChatHistoryMessage,
  ChatHistoryPage,
  UsageOverview,
} from "@/app/admin/usage-report/types";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

const route = ADMIN_ROUTES.USAGE_REPORT;

const PAGE_SIZE = 25;

interface StatTileProps {
  label: string;
  value: string;
}

function StatTile({ label, value }: StatTileProps) {
  return (
    <Card variant="secondary">
      <Section flexDirection="column" alignItems="start" gap={1}>
        <Text text03 secondaryBody>
          {label}
        </Text>
        <Text text05 headingH3>
          {value}
        </Text>
      </Section>
    </Card>
  );
}

function DailyActivityChart({ overview }: { overview: UsageOverview }) {
  if (overview.daily.length === 0) {
    return (
      <EmptyMessageCard
        sizePreset="main-ui"
        title="No activity yet"
        description="Messages will appear here as people use the app."
      />
    );
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={overview.daily}
          margin={{ top: 8, right: 8, bottom: 0, left: -16 }}
        >
          <CartesianGrid
            vertical={false}
            stroke="var(--border-01)"
            strokeDasharray="3 3"
          />
          <XAxis
            dataKey="date"
            tick={{ fill: "var(--text-03)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "var(--border-02)" }}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: "var(--text-03)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            cursor={{ fill: "var(--background-tint-02)" }}
            contentStyle={{
              backgroundColor: "var(--background-neutral-01)",
              border: "1px solid var(--border-02)",
              borderRadius: 8,
              color: "var(--text-05)",
              fontSize: 12,
            }}
            formatter={(value, name) => [
              String(value ?? 0),
              name === "messages" ? "Questions" : String(name),
            ]}
          />
          <Bar
            dataKey="messages"
            name="Questions"
            fill="var(--theme-primary-05)"
            radius={[4, 4, 0, 0]}
            maxBarSize={28}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SessionDetail({ sessionId }: { sessionId: string }) {
  const { data: messages, isLoading } = useSWR<ChatHistoryMessage[]>(
    sessionMessagesUrl(sessionId),
    errorHandlingFetcher
  );

  if (isLoading) {
    return (
      <div className="flex justify-center py-4">
        <SvgSimpleLoader className="h-5 w-5" />
      </div>
    );
  }

  return (
    <Section flexDirection="column" alignItems="start" gap={2}>
      {(messages ?? []).map((message) => (
        <Card
          key={message.id}
          variant={message.message_type === "user" ? "secondary" : "primary"}
        >
          <Section flexDirection="column" alignItems="start" gap={1}>
            <Text text03 secondaryMonoLabel>
              {message.message_type === "user" ? "User" : "Assistant"}
              {message.model_display_name
                ? ` · ${message.model_display_name}`
                : ""}
              {" · "}
              {new Date(message.time_sent).toLocaleString()}
            </Text>
            <Text text04 mainUiBody className="whitespace-pre-wrap break-words">
              {message.message.length > 1500
                ? `${message.message.slice(0, 1500)}…`
                : message.message}
            </Text>
          </Section>
        </Card>
      ))}
    </Section>
  );
}

function UsageReportContent() {
  const [days, setDays] = useState(30);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [expandedSession, setExpandedSession] = useState<string | null>(null);

  const {
    data: overview,
    isLoading: overviewLoading,
    error: overviewError,
  } = useSWR<UsageOverview>(overviewUrl(days), errorHandlingFetcher);

  const { data: history, isLoading: historyLoading } = useSWR<ChatHistoryPage>(
    chatHistoryUrl(days, page, PAGE_SIZE, search),
    errorHandlingFetcher
  );

  if (overviewLoading) {
    return <PageLoader />;
  }

  if (overviewError || !overview) {
    return (
      <ErrorCallout
        errorTitle="Failed to load usage data"
        errorMsg={overviewError?.info?.detail || "An unknown error occurred"}
      />
    );
  }

  const totalPages = history
    ? Math.max(1, Math.ceil(history.total / PAGE_SIZE))
    : 1;

  return (
    <>
      {/* Period + export */}
      <Section flexDirection="row" justifyContent="between" alignItems="center">
        <InputSelect
          value={String(days)}
          onValueChange={(value: string) => {
            setDays(parseInt(value));
            setPage(1);
          }}
        >
          <InputSelect.Trigger placeholder="Period" />
          <InputSelect.Content>
            <InputSelect.Item value="7">Last 7 days</InputSelect.Item>
            <InputSelect.Item value="30">Last 30 days</InputSelect.Item>
            <InputSelect.Item value="90">Last 90 days</InputSelect.Item>
          </InputSelect.Content>
        </InputSelect>
        <Button
          prominence="secondary"
          onClick={() => window.open(exportUrl(days), "_blank")}
        >
          Export CSV
        </Button>
      </Section>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <StatTile label="Questions" value={String(overview.total_messages)} />
        <StatTile label="Sessions" value={String(overview.total_sessions)} />
        <StatTile label="Active users" value={String(overview.active_users)} />
        <StatTile
          label="Tokens"
          value={formatTokens(
            overview.total_input_tokens + overview.total_output_tokens
          )}
        />
        <StatTile
          label="LLM cost"
          value={formatCost(overview.total_cost_cents)}
        />
        <StatTile
          label="Feedback"
          value={`👍 ${overview.feedback_positive} · 👎 ${overview.feedback_negative}`}
        />
      </div>

      {/* Daily activity */}
      <Card variant="primary">
        <ContentAction
          title="Daily Activity"
          description="Questions asked per day."
          sizePreset="main-content"
          variant="section"
        />
        <DailyActivityChart overview={overview} />
      </Card>

      {/* Cost breakdowns */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card variant="primary">
          <ContentAction
            title="By Model"
            sizePreset="main-content"
            variant="section"
          />
          {overview.by_model.length === 0 ? (
            <Text text03 secondaryBody>
              No usage recorded.
            </Text>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="[&>th]:whitespace-nowrap">
                  <TableHead>Model</TableHead>
                  <TableHead>In / Out tokens</TableHead>
                  <TableHead>Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {overview.by_model.map((row) => (
                  <TableRow key={row.model}>
                    <TableCell>
                      <Text text04 mainUiBody>
                        {row.model}
                      </Text>
                    </TableCell>
                    <TableCell>
                      <Text text03 secondaryMono>
                        {formatTokens(row.input_tokens)} /{" "}
                        {formatTokens(row.output_tokens)}
                      </Text>
                    </TableCell>
                    <TableCell>
                      <Text text04 mainUiBody>
                        {formatCost(row.cost_cents)}
                      </Text>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>

        <Card variant="primary">
          <ContentAction
            title="By User"
            sizePreset="main-content"
            variant="section"
          />
          {overview.by_user.length === 0 ? (
            <Text text03 secondaryBody>
              No usage recorded.
            </Text>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="[&>th]:whitespace-nowrap">
                  <TableHead>User</TableHead>
                  <TableHead>In / Out tokens</TableHead>
                  <TableHead>Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {overview.by_user.map((row) => (
                  <TableRow key={row.email}>
                    <TableCell>
                      <Text text04 mainUiBody>
                        {row.email}
                      </Text>
                    </TableCell>
                    <TableCell>
                      <Text text03 secondaryMono>
                        {formatTokens(row.input_tokens)} /{" "}
                        {formatTokens(row.output_tokens)}
                      </Text>
                    </TableCell>
                    <TableCell>
                      <Text text04 mainUiBody>
                        {formatCost(row.cost_cents)}
                      </Text>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>
      </div>

      {/* Chat history */}
      <Card variant="primary">
        <ContentAction
          title="Chat History"
          description="Recent conversations across all users and bots."
          sizePreset="main-content"
          variant="section"
          rightChildren={
            <InputTypeIn
              placeholder="Search..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          }
        />

        {historyLoading ? (
          <div className="flex justify-center py-8">
            <SvgSimpleLoader className="h-6 w-6" />
          </div>
        ) : !history || history.entries.length === 0 ? (
          <EmptyMessageCard
            sizePreset="main-ui"
            title="No conversations"
            description="Nothing matches this period or search."
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow className="[&>th]:whitespace-nowrap">
                  <TableHead>Time</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>First question</TableHead>
                  <TableHead>Messages</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.entries.map((entry) => (
                  <>
                    <TableRow
                      key={entry.session_id}
                      className="cursor-pointer"
                      onClick={() =>
                        setExpandedSession(
                          expandedSession === entry.session_id
                            ? null
                            : entry.session_id
                        )
                      }
                    >
                      <TableCell>
                        <Text text03 secondaryBody nowrap>
                          {new Date(entry.time_created).toLocaleString()}
                        </Text>
                      </TableCell>
                      <TableCell>
                        <Text text04 mainUiBody>
                          {entry.user_email ?? "-"}
                        </Text>
                      </TableCell>
                      <TableCell>
                        <Text text03 secondaryBody>
                          {entry.persona_name ?? "-"}
                        </Text>
                      </TableCell>
                      <TableCell>
                        <Text text04 mainUiBody>
                          {(entry.description ?? "").slice(0, 80) || "-"}
                        </Text>
                      </TableCell>
                      <TableCell>
                        <Text text03 secondaryBody>
                          {entry.message_count}
                        </Text>
                      </TableCell>
                    </TableRow>
                    {expandedSession === entry.session_id && (
                      <TableRow key={`${entry.session_id}-detail`}>
                        <TableCell colSpan={5}>
                          <SessionDetail sessionId={entry.session_id} />
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                ))}
              </TableBody>
            </Table>

            <Section
              flexDirection="row"
              justifyContent="between"
              alignItems="center"
            >
              <Text text03 secondaryBody>
                {history.total} conversations · page {page} / {totalPages}
              </Text>
              <Section
                flexDirection="row"
                justifyContent="end"
                gap={2}
                width="fit"
              >
                <Button
                  prominence="secondary"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  Previous
                </Button>
                <Button
                  prominence="secondary"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                >
                  Next
                </Button>
              </Section>
            </Section>
          </>
        )}
      </Card>
    </>
  );
}

export default function Page() {
  return (
    <SettingsLayouts.Root width="lg">
      <SettingsLayouts.Header
        icon={route.icon}
        title={route.title}
        description="Activity, LLM cost, and chat history across the workspace."
      />
      <SettingsLayouts.Body>
        <UsageReportContent />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
