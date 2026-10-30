import os


class FileService:
    @staticmethod
    def extract_text(filepath: str, ext: str) -> str | None:
        try:
            if ext == ".txt" or ext == ".md":
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()

            elif ext == ".pdf":
                try:
                    import fitz
                    doc = fitz.open(filepath)
                    text = ""
                    for page in doc:
                        text += page.get_text()
                    doc.close()
                    return text
                except ImportError:
                    try:
                        from PyPDF2 import PdfReader
                        reader = PdfReader(filepath)
                        text = ""
                        for page in reader.pages:
                            text += page.extract_text() or ""
                        return text
                    except ImportError:
                        return None

            elif ext == ".docx":
                from docx import Document
                doc = Document(filepath)
                return "\n".join([p.text for p in doc.paragraphs])

        except Exception as e:
            return f"Error extracting text: {str(e)}"

        return None
