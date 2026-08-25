import { useCallback, useEffect, useRef, useState } from "react";

import {
  attachmentDownloadUrl,
  deleteAttachment,
  listAttachments,
  uploadAttachment,
} from "../../api/customers";
import type { Attachment } from "../../types/customer";
import { ErrorBanner, Loading, formatBytes, formatDateTime, styles, tokens } from "../ui";

interface Props {
  customerId: string;
  /** Changing this value forces a reload (e.g. after notes are deleted). */
  reloadKey?: number;
}

export default function AttachmentsPanel({ customerId, reloadKey = 0 }: Props) {
  const [items, setItems] = useState<Attachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listAttachments(customerId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  const upload = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files);
      if (list.length === 0) return;
      setBusy(true);
      setError(null);
      try {
        for (const file of list) {
          await uploadAttachment(customerId, file);
        }
        await load();
      } catch (err) {
        // A 413 from the server surfaces here with its detail message.
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [customerId, load],
  );

  async function handleDelete(attachment: Attachment) {
    setBusy(true);
    setError(null);
    try {
      await deleteAttachment(attachment.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 style={{ fontSize: "1.1rem" }}>Attachments</h2>
      <ErrorBanner message={error} />

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void upload(event.dataTransfer.files);
        }}
        style={{
          ...styles.card,
          borderStyle: "dashed",
          borderColor: dragging ? tokens.accent : tokens.border,
          background: dragging ? tokens.surface : undefined,
          textAlign: "center",
        }}
      >
        <p style={{ margin: "0 0 0.5rem" }}>Drop files here, or</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          aria-label="Upload attachment"
          disabled={busy}
          onChange={(event) => {
            if (event.target.files) void upload(event.target.files);
          }}
        />
        {busy && <p style={styles.muted}>Uploading…</p>}
      </div>

      {loading ? (
        <Loading />
      ) : items.length === 0 ? (
        <p style={styles.muted}>No attachments yet.</p>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>File</th>
              <th style={styles.th}>Type</th>
              <th style={styles.th}>Size</th>
              <th style={styles.th}>Uploaded</th>
              <th style={styles.th} />
            </tr>
          </thead>
          <tbody>
            {items.map((attachment) => (
              <tr key={attachment.id}>
                <td style={styles.td}>
                  <a
                    href={attachmentDownloadUrl(attachment.id)}
                    // The browser handles the stream; Content-Disposition names the file.
                    target="_blank"
                    rel="noreferrer"
                  >
                    {attachment.filename}
                  </a>
                  {attachment.note_id && (
                    <span style={{ ...styles.muted, marginLeft: "0.5rem" }}>(on note)</span>
                  )}
                </td>
                <td style={styles.td}>{attachment.content_type}</td>
                <td style={styles.td}>{formatBytes(attachment.size_bytes)}</td>
                <td style={styles.td}>{formatDateTime(attachment.created_at)}</td>
                <td style={styles.td}>
                  <button
                    type="button"
                    style={styles.button}
                    disabled={busy}
                    onClick={() => void handleDelete(attachment)}
                    aria-label={`Delete ${attachment.filename}`}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
