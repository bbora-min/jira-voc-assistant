import { useEffect, useRef, useCallback } from "react";
import { useEditor, EditorContent, type Editor } from "@tiptap/react";
import { StarterKit } from "@tiptap/starter-kit";
import { Image } from "@tiptap/extension-image";
import { Underline } from "@tiptap/extension-underline";
import { Link } from "@tiptap/extension-link";
import { Table, TableRow, TableCell, TableHeader } from "@tiptap/extension-table";
import { uploadImage } from "@/api/actions";

interface Props {
  initialHtml: string;
  onChange?: (html: string) => void;
  disabled?: boolean;
}

function Toolbar({ editor }: { editor: Editor | null }) {
  const fileRef = useRef<HTMLInputElement>(null);

  const onPickImage = useCallback(() => fileRef.current?.click(), []);

  const onFileChosen = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file || !editor) return;
      try {
        const r = await uploadImage(file);
        editor.chain().focus().setImage({ src: r.url, alt: r.filename }).run();
      } catch (err) {
        console.error("upload failed:", err);
        alert(`이미지 업로드 실패: ${(err as Error).message}`);
      }
    },
    [editor]
  );

  if (!editor) return null;

  const btn = (active: boolean) =>
    `tt-btn${active ? " active" : ""}`;

  return (
    <div className="tt-toolbar">
      <button
        type="button"
        className={btn(editor.isActive("bold"))}
        onClick={() => editor.chain().focus().toggleBold().run()}
      >
        <b>B</b>
      </button>
      <button
        type="button"
        className={btn(editor.isActive("italic"))}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      >
        <i>I</i>
      </button>
      <button
        type="button"
        className={btn(editor.isActive("underline"))}
        onClick={() => editor.chain().focus().toggleUnderline().run()}
      >
        <u>U</u>
      </button>
      <span className="tt-sep" />
      <button
        type="button"
        className={btn(editor.isActive("bulletList"))}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      >
        • 목록
      </button>
      <button
        type="button"
        className={btn(editor.isActive("orderedList"))}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      >
        1. 목록
      </button>
      <span className="tt-sep" />
      <button
        type="button"
        className={btn(editor.isActive("codeBlock"))}
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
      >
        {"</>"}
      </button>
      <button
        type="button"
        className={btn(false)}
        onClick={() =>
          editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
        }
      >
        표
      </button>
      <button type="button" className={btn(false)} onClick={onPickImage}>
        🖼 이미지
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        style={{ display: "none" }}
        onChange={onFileChosen}
      />
      <span className="tt-sep" />
      <button
        type="button"
        className={btn(false)}
        onClick={() => editor.chain().focus().undo().run()}
        title="Ctrl+Z"
      >
        ↶
      </button>
      <button
        type="button"
        className={btn(false)}
        onClick={() => editor.chain().focus().redo().run()}
        title="Ctrl+Shift+Z"
      >
        ↷
      </button>
    </div>
  );
}

export function TiptapEditor({ initialHtml, onChange, disabled = false }: Props) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Underline,
      Image.configure({ inline: false, allowBase64: false }),
      Link.configure({ openOnClick: false, HTMLAttributes: { rel: "noreferrer", target: "_blank" } }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
    ],
    content: initialHtml || "<p></p>",
    editable: !disabled,
    onUpdate({ editor }) {
      onChange?.(editor.getHTML());
    },
  });

  // initialHtml가 외부에서 갱신될 때 (재생성 등) 에디터 내용 동기화
  useEffect(() => {
    if (!editor) return;
    const current = editor.getHTML();
    if (initialHtml && initialHtml !== current) {
      editor.commands.setContent(initialHtml, { emitUpdate: false });
    }
  }, [initialHtml, editor]);

  useEffect(() => {
    if (!editor) return;
    editor.setEditable(!disabled);
  }, [disabled, editor]);

  return (
    <div className={`tt-wrap${disabled ? " tt-disabled" : ""}`}>
      <Toolbar editor={editor} />
      <EditorContent editor={editor} className="tt-content" />
    </div>
  );
}
