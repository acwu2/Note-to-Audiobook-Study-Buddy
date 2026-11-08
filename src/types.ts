export type SourceStatus = 'transcribed' | 'unclear' | 'reading';

/** One photographed page of handwritten notes. */
export interface Source {
  id: string;
  name: string;
  status: SourceStatus;
  /** Number of words the vision model marked [unclear]. */
  unclearCount: number;
  /** Object URL or remote URL of the uploaded photo, when there is one. */
  photoUrl?: string;
  /** Step 1 · Read — what the vision model transcribed. */
  transcript: string;
  /** Step 2 · Prepare — the transcript rewritten for the ear. */
  spoken: string;
  /** Whether this page is used as context for answers. */
  enabled: boolean;
}

export type MessageRole = 'user' | 'assistant' | 'pending';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  /** Source ids the answer is grounded in. */
  citations?: string[];
}

export type SourceTab = 'photo' | 'transcript' | 'spoken';

export interface Voice {
  id: string;
  label: string;
}
