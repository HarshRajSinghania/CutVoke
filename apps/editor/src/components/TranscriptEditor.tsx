import { useEffect, useRef, useState } from "react";
import { useEditor, showError } from "../store/editor";
import { getLatestState, runCommand } from "../store/actions";
import { flushPendingEdits } from "../lib/pendingEdits";
import { previewCommand, type CommandPreview } from "../lib/api";
import { rationalToSecs } from "../lib/rational";
import { AUDITION_RANGE_EVENT, CANCEL_AUDITION_EVENT, transcriptLockedTracks, transcriptSelection, type TranscriptRange } from "../lib/transcript";
import { msg, tr, useLocale } from "../i18n";
import "../styles/transcript.css";

interface Review {
  projectId: string; sequenceId: string; revision: string; key: string; signature: string;
  payload: Record<string, unknown>; preview: CommandPreview;
}

export function TranscriptEditor() {
  useLocale();
  const { state, dispatch } = useEditor({ subscribeToClock: false });
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [wordCaption, setWordCaption] = useState("");
  const [words, setWords] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const operation = useRef(0);
  const [review, setReview] = useState<Review | null>(null);
  const [notice, setNotice] = useState(false);
  const mounted = useRef(true);
  const generation = useRef(0);
  const captions = state.project?.sequence.captions || [];
  const caption = captions.find(item => item.id === wordCaption);
  const selection = { captionIds: selected, captionId: wordCaption, wordIndices: words };
  const selectedKey = JSON.stringify(selection);
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const choice = transcriptSelection(captions, selection);
  const previousChoice = useRef({ key: selectedKey, signature: choice?.signature });
  const locked = state.project && choice ? transcriptLockedTracks(state.project.sequence, choice.ranges) : [];
  const disabled = busy || !!state.editLock || state.opening || !state.project || state.project.revision !== state.revision;
  const reviewValid = !!review && review.projectId === state.currentId && review.sequenceId === state.project?.sequence.id &&
    review.revision === state.revision && review.key === selectedKey && review.signature === choice?.signature && !locked.length;
  const cancelAudition = () => window.dispatchEvent(new Event(CANCEL_AUDITION_EVENT));
  const invalidate = () => { generation.current++; setReview(null); setNotice(false); cancelAudition(); };
  useEffect(() => {
    generation.current++; setSelected([]); setWordCaption(""); setWords([]); setQuery(""); setReview(null); setNotice(false);
    operation.current++; busyRef.current = false; setBusy(false);
    cancelAudition();
  }, [state.currentId, state.project?.sequence.id, state.view]);
  useEffect(() => {
    cancelAudition();
  }, [state.revision]);
  useEffect(() => {
    if (review && review.revision !== state.revision) { setReview(null); setNotice(true); }
  }, [state.revision, review]);
  useEffect(() => {
    const previous = previousChoice.current;
    previousChoice.current = { key: selectedKey, signature: choice?.signature };
    if (previous.key === selectedKey && previous.signature && previous.signature !== choice?.signature) {
      setSelected([]); setWords([]); setReview(null); setNotice(true); cancelAudition();
    }
  }, [selectedKey, choice?.signature]);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; generation.current++; cancelAudition(); };
  }, []);

  const locate = (time: number, captionId?: string) => {
    cancelAudition(); window.dispatchEvent(new Event("cutvoke:pause-play"));
    if (captionId) dispatch({ type: "CAPTION_SELECTION_SET", captionId });
    dispatch({ type: "PLAYHEAD_SET", t: time });
  };
  const audition = (range: TranscriptRange) => {
    if (!state.currentId || !state.project) return;
    window.dispatchEvent(new CustomEvent(AUDITION_RANGE_EVENT, { detail: { ...range,
      projectId: state.currentId, sequenceId: state.project.sequence.id, revision: state.revision } }));
  };
  const stale = (token: number, projectId: string, sequenceId: string) => {
    const latest = getLatestState();
    if (mounted.current && generation.current === token && latest?.currentId === projectId &&
      latest.project?.sequence.id === sequenceId && latest.view === "editor") { setReview(null); setNotice(true); }
  };
  const prepare = async () => {
    if (busyRef.current || disabled || !choice || locked.length || !state.currentId || !state.project) return;
    busyRef.current = true; setBusy(true); setReview(null); setNotice(false); cancelAudition();
    const token = generation.current, projectId = state.currentId, sequenceId = state.project.sequence.id;
    const operationId = ++operation.current;
    const initialSignature = choice.signature, key = selectedKey;
    let previewRevision: string | undefined;
    try {
      if (!await flushPendingEdits()) return;
      const fresh = getLatestState();
      const freshChoice = transcriptSelection(fresh?.project?.sequence.captions || [], selectionRef.current);
      if (!mounted.current || generation.current !== token || JSON.stringify(selectionRef.current) !== key || fresh?.currentId !== projectId ||
        fresh.project?.sequence.id !== sequenceId || fresh.view !== "editor" || fresh.editLock || fresh.project.revision !== fresh.revision ||
        freshChoice?.signature !== initialSignature || transcriptLockedTracks(fresh.project.sequence, freshChoice.ranges).length) { stale(token, projectId, sequenceId); return; }
      const revision = fresh.revision;
      previewRevision = revision;
      const preview = await previewCommand(projectId, "transcript.delete", freshChoice.payload, revision);
      const latest = getLatestState();
      if (!mounted.current || generation.current !== token || JSON.stringify(selectionRef.current) !== key || latest?.currentId !== projectId ||
        latest.project?.sequence.id !== sequenceId || latest.view !== "editor" || latest.revision !== revision || latest.project.revision !== revision || latest.editLock ||
        transcriptSelection(latest.project.sequence.captions || [], selectionRef.current)?.signature !== initialSignature) { stale(token, projectId, sequenceId); return; }
      if (preview.valid && preview.commandType === "transcript.delete")
        setReview({ projectId, sequenceId, revision, key, signature: initialSignature, payload: freshChoice.payload, preview });
    } catch (error) {
      const latest = getLatestState();
      if (mounted.current && generation.current === token && latest?.currentId === projectId && latest.view === "editor" &&
        latest.project?.sequence.id === sequenceId && (previewRevision === undefined || latest.revision === previewRevision)) showError(dispatch, error);
    }
    finally { if (operation.current === operationId) { busyRef.current = false; if (mounted.current) setBusy(false); } }
  };
  const confirm = async () => {
    if (busyRef.current || disabled || !reviewValid || !review) return;
    busyRef.current = true; setBusy(true); cancelAudition();
    const token = generation.current;
    const operationId = ++operation.current;
    try {
      if (!await flushPendingEdits()) return;
      const latest = getLatestState();
      const current = transcriptSelection(latest?.project?.sequence.captions || [], selectionRef.current);
      if (!mounted.current || generation.current !== token || JSON.stringify(selectionRef.current) !== review.key || latest?.currentId !== review.projectId ||
        latest.project?.sequence.id !== review.sequenceId || latest.view !== "editor" || latest.revision !== review.revision || latest.project.revision !== review.revision ||
        latest.editLock || current?.signature !== review.signature || transcriptLockedTracks(latest.project.sequence, current.ranges).length) { stale(token, review.projectId, review.sequenceId); return; }
      // A conflict requires a fresh trial and a new human confirmation, never an automatic retry.
      const isCurrent = () => {
        const current = getLatestState();
        return mounted.current && generation.current === token && current?.currentId === review.projectId &&
          current.view === "editor" && current.project?.sequence.id === review.sequenceId;
      };
      const result = await runCommand(dispatch, latest, "transcript.delete", review.payload, { retryConflict: false, isCurrent });
      if (!isCurrent()) return;
      setReview(null);
      if (result.ok) {
        setSelected([]); setWordCaption(""); setWords([]); setNotice(false);
        dispatch({ type: "STATUS_SET", severity: "ok", text: msg("已删去对应画面与声音，字幕同步收拢，可一次撤销") });
      } else setNotice(true);
    } finally { if (operation.current === operationId) { busyRef.current = false; if (mounted.current) setBusy(false); } }
  };
  if (!captions.length) return null;
  const filtered = captions.filter(item => item.text.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const affectedClips = new Set(review?.preview.changedEntities.filter(item => item.type === "clip").map(item => item.id));
  const affectedCaptions = new Set(review?.preview.changedEntities.filter(item => item.type === "caption").map(item => item.id));
  return <details className="transcript-editor" data-testid="transcript-editor" onToggle={event => { if (!event.currentTarget.open) cancelAudition(); }}>
    <summary className="cv-btn cv-btn--secondary cv-btn--sm">{tr("按文本剪视频")}</summary>
    <p className="cv-hint">{tr("选择句子或词，先试听并预览影响，确认后同步删除画面、声音和字幕。")}</p>
    <input className="cv-input" type="search" aria-label={tr("搜索转写文本")} placeholder={tr("搜索转写文本")}
      value={query} onChange={event => setQuery(event.target.value)} />
    <p className="cv-hint" role="status">{tr("找到 {0} 个句子", filtered.length)}</p>
    <div className="transcript-editor__sentences">
      {filtered.map(item => <div key={item.id} className="transcript-editor__sentence">
        <label><input type="checkbox" disabled={disabled} checked={!wordCaption && selected.includes(item.id)}
          onChange={event => { invalidate(); setWordCaption(""); setWords([]); setSelected(event.target.checked ? [...selected, item.id] : selected.filter(id => id !== item.id)); }} />
          <span><small>{rationalToSecs(item.start).toFixed(2)}–{rationalToSecs(item.end).toFixed(2)}s</small> {item.text}</span></label>
        <div className="transcript-editor__actions">
          <button className="cv-btn cv-btn--secondary cv-btn--sm" onClick={() => locate(rationalToSecs(item.start), item.id)}>{tr("定位")}</button>
          <button className="cv-btn cv-btn--secondary cv-btn--sm" onClick={() => audition({ start: rationalToSecs(item.start), end: rationalToSecs(item.end) })}>{tr("试听")}</button>
          {!!item.words?.length && <button className="cv-btn cv-btn--secondary cv-btn--sm" disabled={disabled}
            onClick={() => { invalidate(); setSelected([]); setWordCaption(item.id); setWords([]); locate(rationalToSecs(item.start), item.id); }}>{tr("按词剪辑")}</button>}
        </div>
      </div>)}
    </div>
    <label className="transcript-editor__word-caption">{tr("按词剪辑")}
      <select className="cv-input" disabled={disabled} value={wordCaption} onChange={event => { invalidate(); setSelected([]); setWordCaption(event.target.value); setWords([]); }}>
        <option value="">{tr("选择有词级时间的句子")}</option>
        {captions.filter(item => item.words?.length).map(item => <option key={item.id} value={item.id}>{item.text}</option>)}
      </select>
    </label>
    <div className="transcript-editor__words">
      {caption?.words?.map((word, index) => <button key={index} className="cv-btn cv-btn--secondary cv-btn--sm" disabled={disabled}
        aria-pressed={words.includes(index)} title={`${rationalToSecs(word.start).toFixed(2)}–${rationalToSecs(word.end).toFixed(2)}s`}
        onClick={() => { invalidate(); setWords(words.includes(index) ? words.filter(i => i !== index) : [...words, index]); locate(rationalToSecs(word.start), caption.id); }}>{word.text}</button>)}
    </div>
    {choice && <div className="transcript-editor__ranges">
      <p>{tr("所选范围：{0} 段，共 {1} 秒（重叠已合并）", choice.ranges.length, choice.duration.toFixed(2))}</p>
      {choice.ranges.map(range => <button key={range.start} className="cv-btn cv-btn--secondary cv-btn--sm" onClick={() => audition(range)}>
        {tr("试听 {0}–{1} 秒", range.start.toFixed(2), range.end.toFixed(2))}</button>)}
    </div>}
    {locked.length > 0 && <p role="status" className="cv-hint">{tr("所选范围会影响锁定轨道，请先解锁再预览。")}</p>}
    {notice && <p role="status" className="cv-hint">{tr("工程或选择已变化，请重新预览后确认。")}</p>}
    <button className="cv-btn cv-btn--secondary cv-btn--sm" disabled={!choice || disabled || !!locked.length} onClick={() => void prepare()}>{tr("预览删除影响")}</button>
    {reviewValid && review && <section className="transcript-editor__review" aria-label={tr("删除影响预览")}>
      <p>{tr("将影响 {0} 个片段和 {1} 条字幕；画面与声音联动收拢，可一次撤销。", affectedClips.size, affectedCaptions.size)}</p>
      <p className="cv-hint">{tr("此预览未修改工程。确认后才会删除。")}</p>
      <button className="cv-btn cv-btn--danger cv-btn--sm" disabled={disabled} onClick={() => void confirm()}>{tr("确认删除所选内容及画面")}</button>
      <button className="cv-btn cv-btn--secondary cv-btn--sm" disabled={busy} onClick={() => { generation.current++; setReview(null); }}>{tr("取消")}</button>
    </section>}
  </details>;
}
