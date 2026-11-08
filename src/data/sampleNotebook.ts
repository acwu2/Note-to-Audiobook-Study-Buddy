import type { ChatMessage, Source, Voice } from '../types';

// Sample content so the UI has something to show before the backend exists.
// Replace with real data from the API once steps 1–4 are wired up.

export const notebookTitle = 'Bio 101 · Cellular respiration';

export const notebookGuide = {
  title: 'Cellular respiration',
  summary:
    'Your notes cover how cells turn glucose into ATP in three stages — glycolysis, the Krebs cycle and the electron transport chain — and where in the cell each one happens.',
};

export const sampleSources: Source[] = [
  {
    id: 'p1',
    name: 'Lecture 4 — page 1',
    status: 'transcribed',
    unclearCount: 0,
    enabled: true,
    transcript:
      'Cellular respiration → ATP\n3 stages:\n1st glycolysis (cytoplasm)\n2nd Krebs cycle (mitochondria)\n3rd ETC — most ATP, ~34\ne.g. glucose + O2 → CO2 + H2O',
    spoken:
      'Cellular respiration leads to A T P.\nThere are three stages.\nFirst, glycolysis, in the cytoplasm.\nSecond, the Krebs cycle, in the mitochondria.\nThird, the electron transport chain, which makes most of the A T P, about thirty-four.\nFor example, glucose plus oxygen leads to carbon dioxide plus water.',
  },
  {
    id: 'p2',
    name: 'Lecture 4 — page 2',
    status: 'unclear',
    unclearCount: 1,
    enabled: true,
    transcript:
      'Krebs cycle = citric acid cycle\nruns 2× per glucose\nmakes NADH + FADH2 → feed ETC\nreleases CO2 [unclear]',
    spoken:
      'The Krebs cycle is also called the citric acid cycle.\nIt runs twice for each glucose molecule.\nIt makes N A D H and F A D H 2, which feed the electron transport chain.\nIt releases carbon dioxide.',
  },
  {
    id: 'p3',
    name: 'Lab handout',
    status: 'reading',
    unclearCount: 0,
    enabled: true,
    transcript: '',
    spoken: '',
  },
];

export const sampleMessages: ChatMessage[] = [
  { id: 'm1', role: 'user', text: 'Explain the second stage like I am new to it.' },
  {
    id: 'm2',
    role: 'assistant',
    text: 'The second stage is the Krebs cycle. It happens inside the mitochondria. Think of it as a loop that takes what is left of glucose after glycolysis and pulls out more energy, giving off carbon dioxide as it goes.\n\nYour notes say it feeds the third stage, the electron transport chain, which is where most of the ATP is made.',
    citations: ['p1', 'p2'],
  },
];

export const suggestedQuestions = [
  'Quiz me with three questions',
  'What did I mark as unclear?',
  'Summarize page 2 in one minute',
];

export const studyTools = [
  { name: 'Quiz me', desc: 'Three spoken questions from your notes', prompt: 'Quiz me with three questions' },
  { name: 'Flashcards', desc: 'Key terms, front and back', prompt: 'Make flashcards from my notes' },
  { name: 'Study guide', desc: 'One page to revise from', prompt: 'Write a one-page study guide' },
  { name: 'Explain simply', desc: 'Each point, like you are new to it', prompt: 'Explain each point like I am new to it' },
];

// Kokoro voice ids (github.com/hexgrad/kokoro).
export const voices: Voice[] = [
  { id: 'af_heart', label: 'Heart · American English' },
  { id: 'af_bella', label: 'Bella · American English' },
  { id: 'am_michael', label: 'Michael · American English' },
  { id: 'bf_emma', label: 'Emma · British English' },
];

export const sampleAudioSeconds = 400;
