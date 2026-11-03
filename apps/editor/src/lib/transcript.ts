import type { Caption, Sequence } from "../types/api";
import { rationalToSecs } from "./rational";

export interface TranscriptRange { start: number; end: number }
export type TranscriptSelection = { captionIds: string[]; captionId: string; wordIndices: number[] };

/** UI seconds are only for display/audition. The edit uses original IDs/indices. */
export function transcriptSelection(captions: Caption[], selection: TranscriptSelection) {
  const { captionIds, captionId, wordIndices } = selection;
  const caption = captions.find(item => item.id === captionId);
  const chosen = captionId ? (caption ? [caption] : []) : captions.filter(item => captionIds.includes(item.id));
  if (captionId ? !caption?.words?.length || !wordIndices.length || wordIndices.some(index => !Number.isInteger(index) || !caption.words?.[index])
    : !captionIds.length || chosen.length !== new Set(captionIds).size) return null;
  const timed = captionId ? wordIndices.map(index => caption!.words![index]) : chosen;
  const ranges: TranscriptRange[] = [];
  for (const item of timed.map(item => ({ start: rationalToSecs(item.start), end: rationalToSecs(item.end) })).sort((a, b) => a.start - b.start)) {
    if (!Number.isFinite(item.start) || !Number.isFinite(item.end) || item.start < 0 || item.end <= item.start) return null;
    const previous = ranges.at(-1);
    if (previous && item.start <= previous.end) previous.end = Math.max(previous.end, item.end);
    else ranges.push({ ...item });
  }
  const payload = captionId ? { captionId, wordIndices: [...new Set(wordIndices)].sort((a, b) => a - b) }
    : { captionIds: [...new Set(captionIds)].sort() };
  return { payload, ranges, duration: ranges.reduce((sum, item) => sum + item.end - item.start, 0),
    signature: JSON.stringify(chosen.map(item => ({ id: item.id, text: item.text, start: item.start, end: item.end, words: item.words }))) };
}

export function transcriptLockedTracks(sequence: Sequence, ranges: TranscriptRange[]) {
  const first = ranges[0]?.start ?? Infinity;
  return sequence.tracks.filter(track => track.locked && track.clips.some(clip => rationalToSecs(clip.timelineEnd) > first));
}

export const AUDITION_RANGE_EVENT = "cutvoke:audition-range";
export const CANCEL_AUDITION_EVENT = "cutvoke:cancel-audition";
export const STOP_AUDITION_AUDIO_EVENT = "cutvoke:stop-audition-audio";
export interface TranscriptAudition extends TranscriptRange { projectId: string; sequenceId: string; revision: string }
