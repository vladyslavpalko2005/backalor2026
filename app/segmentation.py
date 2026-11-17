from __future__ import annotations
from typing import List
from PIL import Image
from .annotations import AnnotationItem
from .pipeline import apply_pipeline


def segment_image( image: Image.Image, steps=None) -> List[AnnotationItem]:
        base_image = apply_pipeline(image, [s for s in (steps or []) if s.step_type not in {"crop", "resize", "rotate"}])
        gray = base_image.convert("L")
        threshold = otsu_threshold(gray)
        width, height = gray.size
        data = list(gray.getdata())
        bin_data = [1 if v <= threshold else 0 for v in data]

        row_sums = [sum(bin_data[y * width:(y + 1) * width]) for y in range(height)]
        row_thresh = max(1, int(width * 0.01))
        line_segments = find_runs(row_sums, row_thresh, min_len=3, gap_tol=2)
        if not line_segments:
            return []

        line_infos: List[dict[str, object]] = []
        for top, bottom in line_segments:
            col_sums = [0] * width
            for y in range(top, bottom + 1):
                row_start = y * width
                for x in range(width):
                    col_sums[x] += bin_data[row_start + x]
            col_thresh = max(1, int((bottom - top + 1) * 0.1))
            col_segments = find_runs(col_sums, col_thresh, min_len=3, gap_tol=2)
            if not col_segments:
                continue
            left = col_segments[0][0]
            right = col_segments[-1][1]
            line_infos.append({
                "top": top,
                "bottom": bottom,
                "left": left,
                "right": right,
                "segments": col_segments,
            })

        if not line_infos:
            return []

        block_gap = max(20, int(height * 0.03))
        line_infos.sort(key=lambda x: int(x["top"]))  # type: ignore[index]
        blocks: List[List[dict[str, object]]] = []
        current_block: List[dict[str, object]] = []
        last_bottom = None
        for line in line_infos:
            top = int(line["top"])  # type: ignore[index]
            if last_bottom is not None and top - last_bottom > block_gap:
                if current_block:
                    blocks.append(current_block)
                current_block = []
            current_block.append(line)
            last_bottom = int(line["bottom"])  # type: ignore[index]
        if current_block:
            blocks.append(current_block)

        items: List[AnnotationItem] = []
        next_id = 1
        for block in blocks:
            block_top = min(int(line["top"]) for line in block)  # type: ignore[index]
            block_bottom = max(int(line["bottom"]) for line in block)  # type: ignore[index]
            block_left = min(int(line["left"]) for line in block)  # type: ignore[index]
            block_right = max(int(line["right"]) for line in block)  # type: ignore[index]

            l1_id = next_id
            next_id += 1
            items.append(AnnotationItem(id=l1_id, level="L1", parent_id=None, bbox=[block_left, block_top, max(1, block_right - block_left), max(1, block_bottom - block_top)]))
            for line in block:
                l2_id = next_id
                next_id += 1
                items.append(AnnotationItem(
                    id=l2_id,
                    level="L2",
                    parent_id=l1_id,
                    bbox=[int(line["left"]), int(line["top"]), max(1, int(line["right"]) - int(line["left"])), max(1, int(line["bottom"]) - int(line["top"]))],
                ))
                segments = line["segments"]  # type: ignore[index]
                for seg_left, seg_right in segments:
                    l3_id = next_id
                    next_id += 1
                    items.append(AnnotationItem(
                        id=l3_id,
                        level="L3",
                        parent_id=l2_id,
                        bbox=[int(seg_left), int(line["top"]), max(1, int(seg_right) - int(seg_left)), max(1, int(line["bottom"]) - int(line["top"]))],
                    ))
        return items

def otsu_threshold( gray: Image.Image) -> int:
        hist = gray.histogram()
        total = sum(hist)
        sum_total = sum(i * hist[i] for i in range(256))
        sum_b = 0
        w_b = 0
        max_var = 0.0
        threshold = 128
        for i in range(256):
            w_b += hist[i]
            if w_b == 0:
                continue
            w_f = total - w_b
            if w_f == 0:
                break
            sum_b += i * hist[i]
            m_b = sum_b / w_b
            m_f = (sum_total - sum_b) / w_f
            var_between = w_b * w_f * (m_b - m_f) ** 2
            if var_between > max_var:
                max_var = var_between
                threshold = i
        return threshold

def find_runs( values: List[int], min_value: int, min_len: int, gap_tol: int) -> List[tuple[int, int]]:
        segments: List[tuple[int, int]] = []
        start = None
        last_above = None
        gap = 0
        for idx, value in enumerate(values):
            if value >= min_value:
                if start is None:
                    start = idx
                last_above = idx
                gap = 0
            else:
                if start is not None:
                    gap += 1
                    if gap > gap_tol:
                        end = last_above if last_above is not None else idx
                        if end - start + 1 >= min_len:
                            segments.append((start, end))
                        start = None
                        last_above = None
                        gap = 0
        if start is not None:
            end = last_above if last_above is not None else start
            if end - start + 1 >= min_len:
                segments.append((start, end))
        return segments