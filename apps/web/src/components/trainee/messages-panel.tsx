"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCheck, Loader2, Phone, Send } from "lucide-react";
import { useState, type FormEvent } from "react";

import {
  fetchTraineeMessages,
  respondFollowupStructured,
  respondFollowupText,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { TraineeMessage } from "@/types/api";

const KEYPAD_OPTIONS = [
  { key: "1", label: "Employed", status: "EMPLOYED" },
  { key: "2", label: "Self-employed", status: "SELF_EMPLOYED" },
  { key: "3", label: "Unemployed", status: "UNEMPLOYED" },
  { key: "4", label: "Studying", status: "FURTHER_STUDY" },
] as const;

function StateTicks({ state }: { state: TraineeMessage["state"] }) {
  if (state === "RESPONDED") {
    return <CheckCheck className="h-4 w-4 text-primary" aria-label="Responded" />;
  }
  if (state === "SENT") {
    return <Check className="h-4 w-4 text-muted-foreground" aria-label="Sent" />;
  }
  return null;
}

function ChatItem({ item }: { item: TraineeMessage }) {
  const queryClient = useQueryClient();
  const [reply, setReply] = useState("");
  const responded = item.state === "RESPONDED";
  const canReply = !responded && item.state !== "MISSED";

  const textReply = useMutation({
    mutationFn: () => respondFollowupText(item.followup_id, reply.trim()),
    onSuccess: () => {
      setReply("");
      void queryClient.invalidateQueries({ queryKey: ["trainee-messages"] });
      void queryClient.invalidateQueries({ queryKey: ["trainee-profile"] });
    },
  });

  const submitReply = (formEvent: FormEvent<HTMLFormElement>) => {
    formEvent.preventDefault();
    if (reply.trim()) {
      textReply.mutate();
    }
  };

  return (
    <div className="space-y-2">
      {/* Outbound tracer bubble (system) */}
      <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-3 shadow-sm">
        <p className="whitespace-pre-line text-sm leading-relaxed">{item.message}</p>
        <p className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
          <span className="font-mono uppercase">{item.channel}</span>·
          <span>{item.milestone}</span>·
          <span>{item.sent_at ? new Date(item.sent_at).toLocaleString("en-GB") : item.due_on}</span>
          <StateTicks state={item.state} />
        </p>
      </div>

      {/* Trainee reply bubble */}
      {responded && item.response && (
        <div className="ml-auto max-w-[85%] rounded-2xl rounded-tr-sm bg-primary px-4 py-3 text-primary-foreground shadow-sm">
          <p className="text-sm leading-relaxed">
            {item.response.raw_text ??
              [
                item.response.employment,
                item.response.job_title,
                item.response.wage ? `${item.response.wage} per month` : null,
              ]
                .filter(Boolean)
                .join(" — ")}
          </p>
          <p className="mt-2 text-right text-[11px] opacity-80">Your reply</p>
        </div>
      )}
      {item.needs_review && (
        <p className="rounded-md bg-marigold-100 px-3 py-2 text-xs text-marigold-800 dark:bg-marigold-950 dark:text-marigold-300">
          Your reply needs a manual check by your training centre before it counts.
        </p>
      )}

      {/* Reply box */}
      {canReply && item.kind === "chat" && (
        <form onSubmit={submitReply} className="ml-auto flex max-w-[85%] gap-2">
          <Input
            value={reply}
            onChange={(inputEvent) => setReply(inputEvent.target.value)}
            placeholder="Type your reply, e.g. I got a job as a welder, 14000 per month"
            aria-label={`Reply to the ${item.milestone} follow-up`}
            maxLength={1000}
          />
          <Button
            type="submit"
            size="icon"
            disabled={textReply.isPending || !reply.trim()}
            aria-label="Send reply"
          >
            {textReply.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <Send className="h-4 w-4" aria-hidden />
            )}
          </Button>
        </form>
      )}
      {textReply.isError && (
        <p role="alert" className="text-xs text-destructive">
          Could not send your reply. Please try again.
        </p>
      )}
    </div>
  );
}

function CallItem({ item }: { item: TraineeMessage }) {
  const queryClient = useQueryClient();
  const [chosen, setChosen] = useState<string | null>(null);
  const responded = item.state === "RESPONDED";
  const canAnswer = !responded && item.state !== "MISSED";

  const keypad = useMutation({
    mutationFn: (status: (typeof KEYPAD_OPTIONS)[number]["status"]) =>
      respondFollowupStructured(item.followup_id, { employment_status: status }),
    onSuccess: (_data, status) => {
      setChosen(status);
      void queryClient.invalidateQueries({ queryKey: ["trainee-messages"] });
      void queryClient.invalidateQueries({ queryKey: ["trainee-profile"] });
    },
  });

  return (
    <div className="max-w-[85%] overflow-hidden rounded-2xl border border-border shadow-sm">
      <div className="flex items-center gap-3 bg-primary px-4 py-3 text-primary-foreground">
        <Phone className="h-5 w-5" aria-hidden />
        <div>
          <p className="text-sm font-medium">Tracer call · {item.milestone}</p>
          <p className="text-xs opacity-80">
            Simulated IVR — answer with the keypad below
          </p>
        </div>
      </div>
      <div className="space-y-3 bg-card px-4 py-3">
        <p className="whitespace-pre-line text-sm leading-relaxed">{item.message}</p>
        {responded && item.response ? (
          <p className="text-sm font-medium text-primary">
            Recorded: {item.response.employment ?? "answer received"}
          </p>
        ) : chosen ? (
          <p className="text-sm text-muted-foreground" role="status">
            Answer recorded — thank you.
          </p>
        ) : canAnswer ? (
          <div className="grid grid-cols-2 gap-2" role="group" aria-label="IVR keypad">
            {KEYPAD_OPTIONS.map((option) => (
              <button
                key={option.key}
                type="button"
                disabled={keypad.isPending}
                onClick={() => keypad.mutate(option.status)}
                className="flex items-center gap-2 rounded-md border border-input px-3 py-2 text-left text-sm transition-colors hover:bg-accent disabled:opacity-50"
              >
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-secondary font-mono text-xs font-semibold text-secondary-foreground">
                  {option.key}
                </span>
                {option.label}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            {item.state === "MISSED" ? "This call window has closed." : "Waiting to be delivered."}
          </p>
        )}
        {keypad.isError && (
          <p role="alert" className="text-xs text-destructive">
            Could not record your answer. Please try again.
          </p>
        )}
      </div>
    </div>
  );
}

export function MessagesPanel() {
  const messages = useQuery({
    queryKey: ["trainee-messages"],
    queryFn: fetchTraineeMessages,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl">Messages</CardTitle>
        <CardDescription>
          Your 3/6/12-month follow-up tracers — simulated WhatsApp chats and IVR calls
        </CardDescription>
      </CardHeader>
      <CardContent>
        {messages.isPending ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading your messages…
          </p>
        ) : messages.isError ? (
          <p className="text-sm text-destructive" role="alert">
            Could not load messages.
          </p>
        ) : messages.data.length === 0 ? (
          <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
            No tracer messages yet. They arrive at 3, 6 and 12 months after certification.
          </p>
        ) : (
          <div className="space-y-6">
            {messages.data.map((item) => (
              <div key={item.followup_id}>
                {item.kind === "call" ? <CallItem item={item} /> : <ChatItem item={item} />}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
