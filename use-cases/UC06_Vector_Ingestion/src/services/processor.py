"""
Document Processor - Enhanced with DLQ and Semantic Chunking
=============================================================

Features:
- Semantic sentence-aware chunking (non più naive char-based)
- Content-hash based idempotency
- Dead Letter Queue error handling
- Page-aware PDF processing
- Smart CSV grouping

Basato su: Soluzione originale + d_studio.docx + k_studio.docx
Autore: Alessandro La Gamba
"""

import pandas as pd
import PyPDF2
import html
import io
import json
import os
import re
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime
import hashlib
import logging
from pathlib import Path
from urllib.parse import quote

from .dlq import get_dlq, FailureReason
from .text_normalizer import normalize_extracted_text

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Enhanced document processor con semantic chunking.
    
    Improvements:
    - Sentence-boundary aware splitting
    - Content hashing per idempotency
    - DLQ integration per error handling
    - Page metadata tracking
    
    Example:
        >>> processor = DocumentProcessor(chunk_size=500, chunk_overlap=50)
        >>> chunks = processor.process_text("Long text...", "doc_id")
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        use_semantic_chunking: bool = True,
        visual_export_root: Optional[str] = None,
        visual_asset_url_base: Optional[str] = None,
        magellano_visual_asset_root: Optional[str] = None
    ):
        """
        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks for context
            use_semantic_chunking: Use sentence-aware splitting (vs naive)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_semantic_chunking = use_semantic_chunking
        self.visual_export_root = Path(
            visual_export_root or os.getenv("VISUAL_EXPORT_ROOT", "data/visual")
        )
        self.visual_asset_url_base = (
            visual_asset_url_base
            if visual_asset_url_base is not None
            else os.getenv("VISUAL_ASSET_URL_BASE", "/visual/asset?path=")
        )
        self.magellano_visual_asset_root = (
            Path(magellano_visual_asset_root)
            if magellano_visual_asset_root
            else Path(os.getenv("MAGELLANO_VISUAL_ASSET_ROOT"))
            if os.getenv("MAGELLANO_VISUAL_ASSET_ROOT")
            else None
        )
        self.pdf_page_image_dpi = int(os.getenv("PDF_PAGE_IMAGE_DPI", "140"))
        self.pdf_page_image_max_pages = int(os.getenv("PDF_PAGE_IMAGE_MAX_PAGES", "250"))
        self.table_visual_fallback_enabled = os.getenv(
            "PDF_TABLE_VISUAL_FALLBACK",
            "true",
        ).lower() in {"1", "true", "yes", "on"}
        
        # Sentence boundary regex (gestisce abbreviazioni comuni)
        self.sentence_pattern = re.compile(
            r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<![A-Z]\.)(?<=\.|\?|\!)\s+',
            re.UNICODE
        )
        
        logger.info(
            f"DocumentProcessor initialized - "
            f"chunk_size={chunk_size}, overlap={chunk_overlap}, "
            f"semantic={use_semantic_chunking}, "
            f"visual_export_root={self.visual_export_root}"
        )
    
    # ========================================================================
    # TEXT PROCESSING
    # ========================================================================
    
    def process_text(
        self,
        text: str,
        source_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Process raw text con semantic chunking.
        
        Args:
            text: Input text
            source_id: Unique identifier
            metadata: Additional metadata
            
        Returns:
            List of chunk dicts con id, content, metadata
        """
        if not text or not text.strip():
            logger.warning(f"Empty text provided for source_id: {source_id}")
            return []
        
        try:
            text = normalize_extracted_text(text, compact=False)
            # Semantic chunking
            if self.use_semantic_chunking:
                chunks = self._split_text_semantic(text)
            else:
                chunks = self._split_text_naive(text)
            
            # Format with metadata
            formatted_chunks = self._format_chunks(
                chunks,
                content_type="text",
                source=source_id,
                extra_metadata=metadata
            )
            
            logger.info(
                f"Processed text '{source_id}': {len(formatted_chunks)} chunks "
                f"(avg {sum(len(c['content']) for c in formatted_chunks) / len(formatted_chunks):.0f} chars/chunk)"
            )
            
            return formatted_chunks
        
        except Exception as e:
            logger.error(f"Failed to process text for {source_id}: {e}")
            
            get_dlq().add_failed_chunk(
                chunk_id=f"{source_id}_text_processing",
                content=text[:1000],
                error=str(e),
                reason=FailureReason.PARSING_ERROR,
                metadata={"source_id": source_id}
            )
            
            raise
    
    def _split_text_semantic(self, text: str) -> List[str]:
        """
        Sentence-aware chunking che preserva context.
        
        Algorithm:
        1. Split text in sentences
        2. Group sentences until chunk_size
        3. Maintain overlap di ultime frasi
        
        Benefits vs naive:
        - Non taglia parole/frasi a metà
        - Preserva semantic boundaries
        - Migliora quality embeddings
        """
        # Split in sentences
        text = normalize_extracted_text(text, compact=False)
        sentences = self.sentence_pattern.split(text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return [text]
        
        chunks = []
        current_chunk = []
        current_size = 0
        
        for sentence in sentences:
            sentence_size = len(sentence)
            
            # Se aggiungere sentence supera chunk_size e current_chunk non è vuoto
            if current_size + sentence_size > self.chunk_size and current_chunk:
                # Salva chunk corrente
                chunks.append(' '.join(current_chunk))
                
                # Inizia nuovo chunk con overlap
                overlap_sentences = []
                overlap_size = 0
                
                # Prendi ultime frasi per overlap
                for prev_sent in reversed(current_chunk):
                    prev_sent_size = len(prev_sent)
                    if overlap_size + prev_sent_size <= self.chunk_overlap:
                        overlap_sentences.insert(0, prev_sent)
                        overlap_size += prev_sent_size
                    else:
                        break
                
                current_chunk = overlap_sentences
                current_size = overlap_size
            
            current_chunk.append(sentence)
            current_size += sentence_size
        
        # Aggiungi ultimo chunk
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks
    
    def _split_text_naive(self, text: str) -> List[str]:
        """
        Naive character-based chunking (fallback).
        
        Note: Può tagliare parole/frasi a metà - non raccomandato
        """
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += self.chunk_size - self.chunk_overlap
        
        return chunks
    
    # ========================================================================
    # STRUCTURED TABLE / FORMULA HELPERS
    # ========================================================================

    def _clean_cell(self, value: Any) -> str:
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        text = normalize_extracted_text(str(value), compact=True)
        return re.sub(r"\s+", " ", text)

    def _rows_to_markdown(self, columns: List[str], rows: List[List[str]]) -> str:
        safe_columns = [self._clean_cell(c) or f"col_{idx + 1}" for idx, c in enumerate(columns)]
        header = "| " + " | ".join(safe_columns) + " |"
        separator = "| " + " | ".join(["---"] * len(safe_columns)) + " |"
        body = []
        for row in rows:
            padded = (row + [""] * len(safe_columns))[: len(safe_columns)]
            body.append("| " + " | ".join(self._clean_cell(cell) for cell in padded) + " |")
        return "\n".join([header, separator, *body])

    def _rows_to_html(self, columns: List[str], rows: List[List[str]]) -> str:
        safe_columns = [self._clean_cell(c) or f"col_{idx + 1}" for idx, c in enumerate(columns)]
        header = "".join(f"<th>{html.escape(column)}</th>" for column in safe_columns)
        body = []
        for row in rows:
            padded = (row + [""] * len(safe_columns))[: len(safe_columns)]
            cells = "".join(f"<td>{html.escape(self._clean_cell(cell))}</td>" for cell in padded)
            body.append(f"<tr>{cells}</tr>")
        return (
            "<table>"
            f"<thead><tr>{header}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody>"
            "</table>"
        )

    def _rows_to_structured_payload(
        self,
        columns: List[str],
        rows: List[List[Any]],
        title: str,
        row_index_start: int = 1,
    ) -> Dict[str, Any]:
        safe_columns = [self._clean_cell(c) or f"col_{idx + 1}" for idx, c in enumerate(columns)]
        safe_rows = [[self._clean_cell(cell) for cell in row] for row in rows]
        records = []
        for row_offset, row in enumerate(safe_rows):
            padded = (row + [""] * len(safe_columns))[: len(safe_columns)]
            records.append({
                "row_number": row_index_start + row_offset,
                "cells": {column: padded[col_idx] for col_idx, column in enumerate(safe_columns)},
            })

        markdown = self._rows_to_markdown(safe_columns, safe_rows)
        table_html = self._rows_to_html(safe_columns, safe_rows)
        table_json = {
            "title": title,
            "columns": [{"index": idx, "name": column} for idx, column in enumerate(safe_columns)],
            "rows": records,
        }
        row_lines = [
            f"row {record['row_number']}: "
            + " | ".join(f"{column}: {record['cells'].get(column, '')}" for column in safe_columns)
            for record in records
        ]
        text = (
            f"Structured table: {title}\n"
            f"Columns: {', '.join(safe_columns)}\n"
            f"{markdown}\n\n"
            "Records:\n" + "\n".join(row_lines)
        )
        return {
            "content": text,
            "metadata": {
                "structured_kind": "table",
                "table_title": title,
                "table_columns": ", ".join(safe_columns),
                "columns": ", ".join(safe_columns),
                "table_row_count": len(records),
                "table_markdown": markdown,
                "table_html": table_html,
                "table_json": json.dumps(table_json, ensure_ascii=False),
            },
        }

    def _dataframe_to_structured_payload(
        self,
        df: pd.DataFrame,
        title: str,
        row_index_start: int = 1,
    ) -> Dict[str, Any]:
        columns = [str(col) for col in df.columns]
        rows = [[self._clean_cell(value) for value in row] for row in df.to_numpy().tolist()]
        payload = self._rows_to_structured_payload(columns, rows, title, row_index_start)
        payload["metadata"]["table_dtypes"] = json.dumps(
            {str(col): str(dtype) for col, dtype in df.dtypes.items()},
            ensure_ascii=False,
        )
        return payload

    def _extract_formula_lines(self, text: str) -> List[Dict[str, Any]]:
        formulas = []
        math_markers = r"=|<=|>=|±|≤|≥|∑|Σ|∫|√|∆|Δ|π|\^|\\frac|\\sum|\\int|->|⇒"
        math_markers = "|".join(
            re.escape(marker)
            for marker in (
                "=",
                "<=",
                ">=",
                "\u00b1",
                "\u2264",
                "\u2265",
                "\u2211",
                "\u03a3",
                "\u222b",
                "\u221a",
                "\u2206",
                "\u0394",
                "\u03c0",
                "^",
                "\\frac",
                "\\sum",
                "\\int",
                "->",
                "\u2192",
                "\u21d2",
            )
        )
        for line_num, raw_line in enumerate(text.splitlines(), start=1):
            line = normalize_extracted_text(raw_line, compact=True)
            if len(line) < 4:
                continue
            has_marker = re.search(math_markers, line)
            has_numbered_equation = re.search(r"\(\s*\d+(?:\.\d+)+\s*\)", line)
            has_var_eq = re.search(r"\b[A-Za-z][A-Za-z0-9_()]*\s*=", line)
            if not (has_marker or has_numbered_equation or has_var_eq):
                continue
            variables = sorted(set(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", line)))[:16]
            formulas.append({
                "line_number": line_num,
                "text": line,
                "latex": self._formula_line_to_latex(line),
                "variables": variables,
            })
        return formulas[:24]

    @staticmethod
    def _formula_line_to_latex(line: str) -> str:
        # Lightweight normalization: real OCR/LaTeX extraction can overwrite this field upstream.
        normalized = normalize_extracted_text(line, compact=True)
        replacements = {
            "≤": r"\\leq",
            "≥": r"\\geq",
            "±": r"\\pm",
            "∑": r"\\sum",
            "Σ": r"\\Sigma",
            "∫": r"\\int",
            "√": r"\\sqrt",
            "π": r"\\pi",
            "→": r"\\to",
            "⇒": r"\\Rightarrow",
        }
        replacements.update({
            "\u2264": r"\\leq",
            "\u2265": r"\\geq",
            "\u00b1": r"\\pm",
            "\u2211": r"\\sum",
            "\u03a3": r"\\Sigma",
            "\u222b": r"\\int",
            "\u221a": r"\\sqrt",
            "\u03c0": r"\\pi",
            "\u2192": r"\\to",
            "\u21d2": r"\\Rightarrow",
        })
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        return normalized

    def _safe_asset_stem(self, filename: str) -> str:
        stem = Path(filename).stem or "document"
        return re.sub(r"[^\w\-\.]+", "_", stem)[:120]

    def _visual_url_for_path(self, asset_path: str) -> str:
        if not self.visual_asset_url_base:
            return asset_path
        if "{path}" in self.visual_asset_url_base:
            return self.visual_asset_url_base.format(path=quote(asset_path, safe=""))
        if self.visual_asset_url_base.endswith("="):
            return self.visual_asset_url_base + quote(asset_path, safe="")
        return self.visual_asset_url_base.rstrip("/") + "/" + quote(asset_path.replace("\\", "/"), safe="/")

    def _page_image_metadata(
        self,
        filename: str,
        page_num: int,
        local_path: Path,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> Dict[str, Any]:
        local_asset_path = local_path.as_posix()
        asset_path = local_asset_path
        if self.magellano_visual_asset_root:
            try:
                rel_path = local_path.relative_to(self.visual_export_root)
            except ValueError:
                rel_path = Path(local_path.name)
            remote_rel_path = rel_path
            if rel_path.parts and self.magellano_visual_asset_root.name == rel_path.parts[0]:
                remote_rel_path = Path(*rel_path.parts[1:]) if len(rel_path.parts) > 1 else Path(local_path.name)
            asset_path = (self.magellano_visual_asset_root / remote_rel_path).as_posix()

        metadata = {
            "image_url": self._visual_url_for_path(local_asset_path),
            "page_image_url": self._visual_url_for_path(local_asset_path),
            "visual_url": self._visual_url_for_path(local_asset_path),
            "asset_path": asset_path,
            "local_asset_path": local_asset_path,
            "visual_asset_kind": "pdf_page_image",
            "visual_source": filename,
            "visual_page": page_num,
        }
        if width is not None:
            metadata["page_image_width"] = width
        if height is not None:
            metadata["page_image_height"] = height
        return metadata

    def _extract_pdf_page_images(
        self,
        file_content: bytes,
        filename: str,
        total_pages: int,
        enabled: bool = True,
    ) -> Dict[int, Dict[str, Any]]:
        if not enabled:
            return {}
        try:
            import fitz  # PyMuPDF
        except Exception as e:
            logger.warning(f"PyMuPDF not available, skipping page image extraction for {filename}: {e}")
            return {}

        page_images: Dict[int, Dict[str, Any]] = {}
        max_pages = min(total_pages, self.pdf_page_image_max_pages)
        safe_stem = self._safe_asset_stem(filename)
        output_dir = self.visual_export_root / "pdf_pages" / safe_stem
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
            zoom = self.pdf_page_image_dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            for zero_idx in range(max_pages):
                page_num = zero_idx + 1
                output_path = output_dir / f"page_{page_num:04d}.png"
                if output_path.exists() and output_path.stat().st_size > 0:
                    page_images[page_num] = self._page_image_metadata(filename, page_num, output_path)
                    continue
                page = doc.load_page(zero_idx)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                pix.save(str(output_path))
                page_images[page_num] = self._page_image_metadata(
                    filename,
                    page_num,
                    output_path,
                    width=pix.width,
                    height=pix.height,
                )
            doc.close()
        except Exception as e:
            logger.warning(f"PDF page image extraction failed for {filename}: {e}")
        return page_images

    def _extract_text_table_blocks(self, text: str) -> List[Dict[str, Any]]:
        blocks = []
        current = []

        def split_row(line: str) -> List[str]:
            if "|" in line:
                cells = [cell.strip() for cell in line.strip("|").split("|")]
            else:
                cells = [cell.strip() for cell in re.split(r"\s{2,}", line.strip())]
            return [cell for cell in cells if cell]

        def flush_block():
            nonlocal current
            if len(current) < 2:
                current = []
                return
            rows = [split_row(line) for line in current]
            widths = [len(row) for row in rows]
            if max(widths, default=0) < 2:
                current = []
                return
            columns = rows[0]
            data_rows = rows[1:]
            if len(columns) != max(widths):
                columns = [f"col_{idx + 1}" for idx in range(max(widths))]
                data_rows = rows
            blocks.append({"columns": columns, "rows": data_rows})
            current = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            cells = split_row(line) if line else []
            looks_tabular = len(cells) >= 3 or (len(cells) >= 2 and re.search(r"\d", line))
            if looks_tabular:
                current.append(line)
            else:
                flush_block()
        flush_block()
        return blocks[:8]

    def _page_has_table_visual_signal(self, text: str) -> bool:
        value = normalize_extracted_text(text or "", compact=False)
        if not value:
            return False
        if re.search(
            r"\b(tabell[ae]|table|prospetto|quadro|appendice|colonn[ae]|rig[ao]|\brigo\b)\b",
            value,
            flags=re.IGNORECASE,
        ):
            return True
        tabular_lines = 0
        for raw_line in value.splitlines():
            line = normalize_extracted_text(raw_line, compact=True)
            if not line:
                continue
            cells = [cell for cell in re.split(r"\s{2,}|\|", line) if cell.strip()]
            has_numeric_columns = len(re.findall(r"\b\d+(?:[.,]\d+)?\b", line)) >= 3
            if len(cells) >= 3 or has_numeric_columns:
                tabular_lines += 1
            if tabular_lines >= 2:
                return True
        return False

    def _table_visual_fallback_payload(
        self,
        filename: str,
        page_num: int,
        page_text: str,
    ) -> Dict[str, Any]:
        page_text = normalize_extracted_text(page_text or "", compact=False)
        lines = [
            normalize_extracted_text(line, compact=True)
            for line in page_text.splitlines()
            if normalize_extracted_text(line, compact=True)
        ]
        table_like = [
            line for line in lines
            if re.search(r"tabell[ae]|table|prospetto|quadro|appendice|colonn[ae]|rig[ao]|\brigo\b", line, re.I)
            or len(re.findall(r"\b\d+(?:[.,]\d+)?\b", line)) >= 3
        ]
        snippet = " ".join((table_like or lines)[:8])[:900]
        title = f"{filename} page {page_num} table screenshot fallback"
        content = (
            f"Table visual fallback: {title}\n"
            "Il testo della pagina suggerisce contenuto tabellare, ma "
            "l'estrazione non ha prodotto righe strutturate affidabili. "
            "Usare lo screenshot della pagina come asset visuale per verificare "
            "layout, colonne, righe e note.\n"
            f"Estratto OCR: {snippet}"
        )
        return {
            "content": content,
            "metadata": {
                "structured_kind": "table_visual_fallback",
                "table_title": title,
                "table_extractor": "page_screenshot_fallback",
                "table_row_count": 0,
                "requires_visual_table_reading": True,
            },
        }

    def _extract_pdf_tables_with_pdfplumber(self, file_content: bytes, filename: str) -> Dict[int, List[Dict[str, Any]]]:
        try:
            import pdfplumber  # type: ignore
        except Exception:
            return {}

        tables_by_page: Dict[int, List[Dict[str, Any]]] = {}
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_tables = []
                    for table_idx, table in enumerate(page.extract_tables() or [], start=1):
                        rows = [
                            [self._clean_cell(cell) for cell in row]
                            for row in table
                            if row and any(self._clean_cell(cell) for cell in row)
                        ]
                        if len(rows) < 2:
                            continue
                        columns = rows[0]
                        data_rows = rows[1:]
                        title = f"{filename} page {page_num} table {table_idx}"
                        payload = self._rows_to_structured_payload(columns, data_rows, title)
                        payload["metadata"]["table_extractor"] = "pdfplumber"
                        page_tables.append(payload)
                    if page_tables:
                        tables_by_page[page_num] = page_tables
        except Exception as e:
            logger.warning(f"pdfplumber table extraction failed for {filename}: {e}")
        return tables_by_page

    def _formula_metadata(self, formulas: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not formulas:
            return {}
        formula_text = "\n".join(f["text"] for f in formulas)
        formula_latex = "\n".join(f.get("latex") or f["text"] for f in formulas)
        return {
            "structured_kind": "formula",
            "has_formula": True,
            "formula_count": len(formulas),
            "formula_latex": formula_latex,
            "formula_text": formula_text,
            "formulas_json": json.dumps(formulas, ensure_ascii=False),
        }

    # ========================================================================
    # PDF PROCESSING
    # ========================================================================
    
    def process_pdf(
        self,
        file_content: bytes,
        filename: str,
        extract_page_images: Optional[bool] = None,
        extract_tables: bool = True,
        extract_formulas: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Process PDF con page-aware chunking.
        
        Features:
        - Extracta text per page
        - Mantiene page metadata
        - DLQ per pagine corrupted
        - Semantic chunking per page
        
        Args:
            file_content: PDF bytes
            filename: Source filename
            
        Returns:
            List of chunks con page metadata
        """
        try:
            import PyPDF2
            
            # Verifica che sia un PDF valido
            if len(file_content) < 100:  # PDF minimo
                raise ValueError("File troppo piccolo per essere un PDF valido")
            
            # Controlla header PDF
            if not file_content.startswith(b'%PDF'):
                logger.warning(f"File {filename} non ha header PDF valido")
            
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            total_pages = len(pdf_reader.pages)
            
            # Verifica pagina minima
            if total_pages == 0:
                logger.warning(f"PDF {filename} ha 0 pagine")
                # Return empty chunks instead of raising
                return []
            
            logger.info(f"Processing PDF '{filename}': {total_pages} pages")
            
            all_chunks = []
            if extract_page_images is None:
                extract_page_images = os.getenv("PDF_EXTRACT_PAGE_IMAGES", "true").lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            page_images = self._extract_pdf_page_images(
                file_content,
                filename,
                total_pages,
                enabled=extract_page_images,
            )
            extracted_tables = (
                self._extract_pdf_tables_with_pdfplumber(file_content, filename)
                if extract_tables
                else {}
            )
            
            for page_num, page in enumerate(pdf_reader.pages, start=1):
                try:
                    # Extract page text
                    page_text = normalize_extracted_text(page.extract_text() or "", compact=False)
                    
                    if not page_text or not page_text.strip():
                        logger.warning(
                            f"{filename} page {page_num}: Empty page, skipping"
                        )
                        continue
                    
                    # Chunk page text
                    if self.use_semantic_chunking:
                        page_chunks = self._split_text_semantic(page_text)
                    else:
                        page_chunks = self._split_text_naive(page_text)

                    page_tables = extracted_tables.get(page_num)
                    if not page_tables:
                        page_tables = []
                        for table_idx, table in enumerate(
                            self._extract_text_table_blocks(page_text) if extract_tables else [],
                            start=1,
                        ):
                            title = f"{filename} page {page_num} table {table_idx}"
                            payload = self._rows_to_structured_payload(
                                table["columns"],
                                table["rows"],
                                title,
                            )
                            payload["metadata"]["table_extractor"] = "text_heuristic"
                            page_tables.append(payload)

                    if (
                        self.table_visual_fallback_enabled
                        and extract_tables
                        and not page_tables
                        and page_images.get(page_num)
                        and self._page_has_table_visual_signal(page_text)
                    ):
                        fallback_payload = self._table_visual_fallback_payload(
                            filename,
                            page_num,
                            page_text,
                        )
                        fallback_content = fallback_payload["content"]
                        all_chunks.append({
                            "id": self._generate_chunk_id(
                                f"{filename}_page_{page_num}_table_visual_fallback",
                                fallback_content,
                            ),
                            "content": fallback_content,
                            "metadata": {
                                "source": filename,
                                "type": "pdf_table_visual",
                                "page": page_num,
                                "section": "table screenshot fallback",
                                "total_pages": total_pages,
                                "timestamp": datetime.utcnow().isoformat(),
                                "content_hash": self._generate_content_hash(fallback_content),
                                **page_images.get(page_num, {}),
                                **fallback_payload["metadata"],
                            },
                        })

                    for table_idx, table_payload in enumerate(page_tables, start=1):
                        table_content = table_payload["content"]
                        metadata = {
                            "source": filename,
                            "type": "pdf_table",
                            "page": page_num,
                            "section": f"table {table_idx}",
                            "total_pages": total_pages,
                            "timestamp": datetime.utcnow().isoformat(),
                            "content_hash": self._generate_content_hash(table_content),
                            **page_images.get(page_num, {}),
                            **table_payload["metadata"],
                        }
                        all_chunks.append({
                            "id": self._generate_chunk_id(
                                f"{filename}_page_{page_num}_table_{table_idx}",
                                table_content,
                            ),
                            "content": table_content,
                            "metadata": metadata,
                        })
                    
                    # Add page metadata
                    for chunk_idx, chunk_text in enumerate(page_chunks):
                        formula_meta = (
                            self._formula_metadata(self._extract_formula_lines(chunk_text))
                            if extract_formulas
                            else {}
                        )
                        all_chunks.append({
                            "id": self._generate_chunk_id(filename, chunk_text),
                            "content": chunk_text,
                            "metadata": {
                                "source": filename,
                                "type": "pdf",
                                "page": page_num,
                                "total_pages": total_pages,
                                "chunk_index_in_page": chunk_idx,
                                "timestamp": datetime.utcnow().isoformat(),
                                "content_hash": self._generate_content_hash(chunk_text),
                                **page_images.get(page_num, {}),
                                **formula_meta,
                            }
                        })
                
                except Exception as page_error:
                    # Page-level error: log ma continua
                    logger.error(
                        f"Failed to process {filename} page {page_num}: {page_error}"
                    )
                    
                    get_dlq().add_failed_chunk(
                        chunk_id=f"{filename}_page_{page_num}",
                        content=f"Page {page_num} of {filename}",
                        error=str(page_error),
                        reason=FailureReason.PARSING_ERROR,
                        metadata={
                            "filename": filename,
                            "page": page_num,
                            "total_pages": total_pages
                        }
                    )
            
            if not all_chunks:
                logger.warning(f"No valid content extracted from {filename}")
                return []
            
            logger.info(
                f"PDF processed successfully: {len(all_chunks)} chunks from "
                f"{total_pages} pages"
            )
            
            return all_chunks
        
        except PyPDF2.errors.PdfReadError as e:
            logger.error(f"PDF malformato: {filename} - {e}")
            raise ValueError(f"PDF non valido: {filename}")
        except Exception as e:
            logger.error(f"Failed to process PDF {filename}: {e}")
            
            # File-level error
            get_dlq().add_failed_file(
                filename=filename,
                error=str(e),
                reason=FailureReason.PARSING_ERROR,
                file_size_bytes=len(file_content)
            )
            
            raise
    
    # ========================================================================
    # CSV PROCESSING
    # ========================================================================
    
    def process_csv(
        self,
        file_content: bytes,
        filename: str,
        group_by: Optional[str] = None,
        max_rows_per_chunk: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Process CSV con smart grouping.
        
        Strategies:
        1. Group by column (semantic grouping)
        2. Fixed row batches (default)
        
        Args:
            file_content: CSV bytes
            filename: Source filename
            group_by: Column name per semantic grouping
            max_rows_per_chunk: Max rows per chunk
            
        Returns:
            List of chunks
        """
        try:
            df = pd.read_csv(io.BytesIO(file_content))
            chunks_data = []
            
            logger.info(
                f"Processing CSV '{filename}': {len(df)} rows, "
                f"{len(df.columns)} columns"
            )
            
            # Strategy 1: Group by column
            if group_by and group_by in df.columns:
                logger.info(f"Using semantic grouping by column: {group_by}")
                
                for group_value, group_df in df.groupby(group_by):
                    row_start = int(group_df.index.min()) + 1
                    row_end = int(group_df.index.max()) + 1
                    title = f"{filename} {group_by}: {group_value}"
                    structured = self._dataframe_to_structured_payload(
                        group_df,
                        title,
                        row_index_start=row_start,
                    )
                    combined_text = structured["content"]
                    
                    chunks_data.append({
                        "id": self._generate_chunk_id(filename, combined_text),
                        "content": combined_text,
                        "metadata": {
                            "source": filename,
                            "type": "csv",
                            "section": f"{group_by}: {group_value}",
                            "group_by": group_by,
                            "group_value": str(group_value),
                            "columns": ", ".join(str(col) for col in df.columns),
                            "row_range_start": row_start,
                            "row_range_end": row_end,
                            "row_count": len(group_df),
                            "timestamp": datetime.utcnow().isoformat(),
                            "content_hash": self._generate_content_hash(combined_text),
                            **structured["metadata"],
                        }
                    })
            
            # Strategy 2: Fixed row batches
            else:
                logger.info(f"Using fixed batches: {max_rows_per_chunk} rows/chunk")
                
                for i in range(0, len(df), max_rows_per_chunk):
                    batch_df = df.iloc[i:i + max_rows_per_chunk]
                    row_start = i + 1
                    row_end = min(i + max_rows_per_chunk, len(df))
                    title = f"{filename} rows {row_start}-{row_end}"
                    structured = self._dataframe_to_structured_payload(
                        batch_df,
                        title,
                        row_index_start=row_start,
                    )
                    combined_text = structured["content"]
                    
                    chunks_data.append({
                        "id": self._generate_chunk_id(filename, combined_text),
                        "content": combined_text,
                        "metadata": {
                            "source": filename,
                            "type": "csv",
                            "section": f"rows {row_start}-{row_end}",
                            "columns": ", ".join(str(col) for col in df.columns),
                            "row_range_start": row_start,
                            "row_range_end": row_end,
                            "row_count": len(batch_df),
                            "timestamp": datetime.utcnow().isoformat(),
                            "content_hash": self._generate_content_hash(combined_text),
                            **structured["metadata"],
                        }
                    })
            
            logger.info(
                f"CSV processed successfully: {len(chunks_data)} chunks from "
                f"{len(df)} rows"
            )
            
            return chunks_data
        
        except Exception as e:
            logger.error(f"Failed to process CSV {filename}: {e}")
            
            get_dlq().add_failed_file(
                filename=filename,
                error=str(e),
                reason=FailureReason.PARSING_ERROR,
                file_size_bytes=len(file_content)
            )
            
            raise
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def _generate_content_hash(self, content: str) -> str:
        """
        Generate deterministic hash per idempotency.
        
        Benefits:
        - Re-ingestion dello stesso content → stesso ID
        - ChromaDB fa upsert invece di duplicate
        - Deduplication automatica
        
        Args:
            content: Text content
            
        Returns:
            str: SHA256 hash (16 chars)
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
    def _generate_chunk_id(self, source: str, content: str) -> str:
        """
        Generate unique chunk ID basato su content hash.
        
        Format: {source}_{content_hash}
        
        Args:
            source: Source filename/id
            content: Chunk content
            
        Returns:
            str: Deterministic chunk ID
        """
        content_hash = self._generate_content_hash(content)
        # Sanitize source name
        source_clean = re.sub(r'[^\w\-]', '_', source)
        return f"{source_clean}_{content_hash}"
    
    def _format_chunks(
        self,
        chunks: List[str],
        content_type: str,
        source: str,
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Format chunks con metadata standard.
        
        Args:
            chunks: List of text chunks
            content_type: 'text', 'pdf', 'csv'
            source: Source identifier
            extra_metadata: Additional metadata
            
        Returns:
            List of formatted chunk dicts
        """
        formatted = []
        
        for chunk_text in chunks:
            chunk_text = normalize_extracted_text(chunk_text, compact=False)
            # Base metadata
            meta = {
                "source": source,
                "type": content_type,
                "timestamp": datetime.utcnow().isoformat(),
                "content_hash": self._generate_content_hash(chunk_text),
                "chunk_length": len(chunk_text)
            }
            
            # Merge extra metadata
            if extra_metadata:
                meta.update(extra_metadata)
            
            formatted.append({
                "id": self._generate_chunk_id(source, chunk_text),
                "content": chunk_text,
                "metadata": meta
            })
        
        return formatted


if __name__ == "__main__":
    # Test processor
    logging.basicConfig(level=logging.INFO)
    
    processor = DocumentProcessor(chunk_size=200, chunk_overlap=30)
    
    # Test text
    text = """
    L'intelligenza artificiale sta trasformando il mondo. 
    Machine learning e deep learning sono tecnologie fondamentali. 
    Il natural language processing consente alle macchine di comprendere il linguaggio. 
    Computer vision rivoluziona l'analisi delle immagini.
    """ * 3
    
    chunks = processor.process_text(text, "test_doc", {"test": True})
    
    print(f"\n=== Processed {len(chunks)} chunks ===")
    for i, chunk in enumerate(chunks[:3], 1):
        print(f"\nChunk {i}:")
        print(f"  ID: {chunk['id']}")
        print(f"  Length: {len(chunk['content'])} chars")
        print(f"  Content: {chunk['content'][:100]}...")
