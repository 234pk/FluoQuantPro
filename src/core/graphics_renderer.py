import numpy as np
import cv2
import math
from typing import List, Tuple
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QBrush, QFont, QPainterPath, QPolygonF
from PySide6.QtCore import Qt, QPointF, QRectF
from src.utils.physical_style import PhysicalRenderStyle

class GraphicsRenderer:
    """
    Dedicated module for graphics-related rendering tasks.
    Handles annotations, scale bars, and smooth shape generation.
    """

    @staticmethod
    def generate_smooth_polygon_points(points: List[Tuple[int, int]], tension: float = 0.5, num_segments: int = 16) -> np.ndarray:
        """
        Generates smooth points for a closed polygon using Catmull-Rom splines.
        """
        if len(points) < 3:
            return np.array(points, np.int32).reshape((-1, 1, 2))

        points_array = np.array(points)
        count = len(points)
        
        smooth_points = []
        
        for i in range(count):
            p0 = points_array[i - 1] # Previous
            p1 = points_array[i]     # Current
            p2 = points_array[(i + 1) % count] # Next
            p3 = points_array[(i + 2) % count] # Next Next
            
            for t_step in range(num_segments):
                t = t_step / num_segments
                
                t2 = t * t
                t3 = t2 * t
                
                x = 0.5 * ((2 * p1[0]) + 
                           (-p0[0] + p2[0]) * t + 
                           (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + 
                           (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
                           
                y = 0.5 * ((2 * p1[1]) + 
                           (-p0[1] + p2[1]) * t + 
                           (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + 
                           (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
                           
                smooth_points.append([int(x), int(y)])
                
        return np.array(smooth_points, np.int32).reshape((-1, 1, 2))

    @staticmethod
    def apply_scale_bar(image: np.ndarray, settings, original_size: Tuple[int, int] = None, dpi: float = 300.0, screen_dpi: float = 96.0) -> np.ndarray:
        """
        Draws a scale bar on the image using QPainter.
        """
        if not settings.enabled:
            return image
            
        h, w = image.shape[:2]
        
        # 1. Determine Pixel Scale (for WYSIWYG)
        if original_size:
            orig_h, orig_w = original_size
            pixel_scale = float(w) / float(orig_w)
        else:
            pixel_scale = 1.0

        # Physical Scaling
        scale_ratio = PhysicalRenderStyle.get_scale_factor(w)
        
        # 2. Calculate Scale Bar Length in target pixels
        pix_size = settings.pixel_size if settings.pixel_size > 0 else 1.0
        effective_pix_size = pix_size / pixel_scale
        length_px = settings.bar_length_um / effective_pix_size
        
        if length_px <= 0 or length_px > w * 0.9:
            return image

        # 3. Initialize QPainter
        is_float = image.dtype == np.float32
        image_uint8 = (np.clip(image, 0, 1) * 255).astype(np.uint8) if is_float else image
        image_uint8 = np.ascontiguousarray(image_uint8)
        
        # Convert BGR (OpenCV) to RGB for QImage if needed, but here we assume RGB input
        qimg = QImage(image_uint8.data, w, h, w * 3, QImage.Format.Format_RGB888)
        
        painter = QPainter(qimg)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        # 4. Determine Position
        margin = 40 * scale_ratio
        
        if settings.position == "Custom" and settings.custom_pos:
            cx, cy = settings.custom_pos
            x = cx * pixel_scale
            y = cy * pixel_scale
        else:
            if settings.position == "Bottom Right":
                x = w - length_px - margin
                y = h - margin
            elif settings.position == "Bottom Left":
                x = margin
                y = h - margin
            elif settings.position == "Top Right":
                x = w - length_px - margin
                y = margin
            elif settings.position == "Top Left":
                x = margin
                y = margin
            else:
                x, y = margin, margin

        # Boundary Check
        x = max(margin, min(x, w - length_px - margin))
        y = max(margin, min(y, h - margin))

        # 5. Draw Bar
        color = QColor(settings.color)
        thickness = max(1.0, settings.thickness * scale_ratio)
        
        pen = QPen(color, thickness)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, y), QPointF(x + length_px, y))
        
        # 6. Draw Label
        if settings.show_label:
            font_size = max(6, settings.font_size * scale_ratio)
            font = QFont("Arial")
            font.setPointSizeF(font_size)
            painter.setFont(font)
            painter.setPen(color)
            label = f"{settings.bar_length_um} \u00B5m"
            
            text_rect = QRectF(x - margin, y + thickness, length_px + 2*margin, font_size * 1.5)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)
            
        painter.end()
        
        # 7. Back to Numpy
        ptr = qimg.constBits()
        arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 3))
        return arr.astype(np.float32) / 255.0 if is_float else arr.copy()

    @staticmethod
    def draw_dashed_line(image: np.ndarray, pt1: Tuple[int, int], pt2: Tuple[int, int], color: Tuple[float, float, float], thickness: int, dash_length: int = 10, dash_gap: int = 5):
        dist = math.sqrt((pt1[0] - pt2[0])**2 + (pt1[1] - pt2[1])**2)
        if dist < 1: return

        dx = (pt2[0] - pt1[0]) / dist
        dy = (pt2[1] - pt1[1]) / dist

        total_step = dash_length + dash_gap
        if total_step < 1: total_step = 1

        num_segments = int(dist / total_step) + 1

        for i in range(num_segments):
            start_dist = i * total_step
            end_dist = start_dist + dash_length

            if start_dist > dist: break
            if end_dist > dist: end_dist = dist

            p1 = (int(pt1[0] + start_dist * dx), int(pt1[1] + start_dist * dy))
            p2 = (int(pt1[0] + end_dist * dx), int(pt1[1] + end_dist * dy))

            cv2.line(image, p1, p2, color, thickness, cv2.LINE_AA)

    @staticmethod
    def draw_dashed_polyline(image: np.ndarray, pts: np.ndarray, is_closed: bool, color: Tuple[float, float, float], thickness: int, dash_length: int = 10, dash_gap: int = 5):
        count = len(pts)
        if count < 2:
            return
            
        for i in range(count - 1):
            GraphicsRenderer.draw_dashed_line(image, tuple(pts[i][0]), tuple(pts[i+1][0]), color, thickness, dash_length, dash_gap)
            
        if is_closed:
            GraphicsRenderer.draw_dashed_line(image, tuple(pts[-1][0]), tuple(pts[0][0]), color, thickness, dash_length, dash_gap)

    @staticmethod
    def apply_annotations(image: np.ndarray, annotations: List, original_size: Tuple[int, int] = None, dpi: float = 300.0, view_scale: float = 1.0, screen_dpi: float = 96.0) -> np.ndarray:
        if not annotations:
            return image
            
        h, w = image.shape[:2]
        
        if original_size:
            orig_h, orig_w = original_size
        else:
            orig_h, orig_w = h, w

        scale_ratio = PhysicalRenderStyle.get_scale_factor(dpi) * view_scale
        scale_x, scale_y = (float(w) / float(orig_w)), (float(h) / float(orig_h))

        overlay = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        overlay.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(overlay)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        for ann in annotations:
            if not getattr(ann, 'visible', True):
                continue
                
            qcolor = QColor(ann.color)
            base_thickness = float(ann.properties.get('thickness', 2.0))
            thickness = max(1.0, base_thickness * scale_ratio)
            
            pen = QPen(qcolor, thickness)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            
            style = ann.properties.get('style', 'solid')
            if style == 'dashed':
                dash_len = float(ann.properties.get('dash_length', 10)) * scale_ratio
                dash_gap = float(ann.properties.get('dash_gap', 5)) * scale_ratio
                pen.setStyle(Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([dash_len / thickness, dash_gap / thickness])
            elif style == 'dotted':
                dot_spacing = float(ann.properties.get('dot_spacing', 3)) * scale_ratio
                gap_ratio = dot_spacing / thickness
                pen.setDashPattern([0.01, gap_ratio])
            else:
                pen.setStyle(Qt.PenStyle.SolidLine)
            
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            # 1. Coordinate Scaling
            # We use QTransform for efficient path scaling
            from PySide6.QtGui import QTransform
            transform = QTransform().scale(scale_x, scale_y)
            
            # 2. Get Path (Directly from ROI if possible)
            path = getattr(ann, 'path', QPainterPath())
            if path.isEmpty():
                # Fallback: Reconstruct path from points if path is missing
                pts = getattr(ann, 'points', [])
                if pts:
                    qpts = []
                    for p in pts:
                        if isinstance(p, QPointF):
                            qpts.append(p)
                        else:
                            qpts.append(QPointF(p[0], p[1]))
                    
                    qpoly = QPolygonF(qpts)
                    path.addPolygon(qpoly)
                    ann_type = getattr(ann, 'type', getattr(ann, 'roi_type', 'general'))
                    if ann_type not in ["line", "line_scan", "arrow"]:
                        path.closeSubpath()

            if path.isEmpty():
                continue

            # Scale the path to export resolution
            scaled_path = transform.map(path)
            
            painter.save()

            # 3. Handle Rotation
            ann_type = getattr(ann, 'type', getattr(ann, 'roi_type', 'general'))
            rotation = float(ann.properties.get('rotation', 0.0))
            if abs(rotation) > 0.01:
                center = scaled_path.boundingRect().center()
                if not center.isNull():
                    painter.translate(center)
                    painter.rotate(rotation)
                    painter.translate(-center)

            # 4. Rendering by Type
            if ann_type == 'arrow':
                # For arrows, we still need points to draw the head
                qpts = [scaled_path.elementAt(i) for i in range(scaled_path.elementCount())]
                if len(qpts) >= 2:
                    start = QPointF(qpts[0].x, qpts[0].y)
                    end = QPointF(qpts[-1].x, qpts[-1].y)
                    painter.drawLine(start, end)
                    
                    # --- Arrowhead should always be solid ---
                    painter.save()
                    temp_pen = QPen(pen)
                    temp_pen.setStyle(Qt.PenStyle.SolidLine)
                    painter.setPen(temp_pen)
                    
                    head_size = float(ann.properties.get('arrow_head_size', 15.0)) * scale_ratio
                    dx = end.x() - start.x()
                    dy = end.y() - start.y()
                    angle = math.atan2(dy, dx)
                    
                    head_shape = ann.properties.get('arrow_head_shape', 'open')
                    arrow_angle = math.pi / 6
                    p1 = QPointF(end.x() - head_size * math.cos(angle - arrow_angle),
                                 end.y() - head_size * math.sin(angle - arrow_angle))
                    p2 = QPointF(end.x() - head_size * math.cos(angle + arrow_angle),
                                 end.y() - head_size * math.sin(angle + arrow_angle))
                    
                    if head_shape == 'open':
                        painter.drawLine(end, p1)
                        painter.drawLine(end, p2)
                    else: # triangle
                        painter.setBrush(QBrush(qcolor))
                        painter.drawPolygon([end, p1, p2])
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                    
                    painter.restore()

            elif ann_type == 'text':
                text = ann.properties.get('text', '')
                if text:
                    font_size = float(ann.properties.get('font_size', 12.0)) * scale_ratio
                    font = QFont("Arial")
                    font.setPixelSize(int(max(8, font_size)))
                    font.setBold(True)
                    painter.setFont(font)
                    painter.setBrush(QBrush(qcolor))
                    # Use the first point of the path for text position
                    if scaled_path.elementCount() > 0:
                        el = scaled_path.elementAt(0)
                        painter.drawText(QPointF(el.x, el.y), text)
            
            else:
                # Default: Draw the scaled path directly (handles polygon, magic_wand, rect, ellipse, etc.)
                painter.drawPath(scaled_path)
            
            painter.restore()

        painter.end()
        
        ptr = overlay.constBits()
        ov_arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4))
        
        alpha = ov_arr[..., 3].astype(np.float32) / 255.0
        rgb_ov = ov_arr[..., :3].astype(np.float32) / 255.0
        
        if image.dtype != np.float32:
            img_float = image.astype(np.float32)
            if image.dtype == np.uint8: img_float /= 255.0
            elif image.dtype == np.uint16: img_float /= 65535.0
        else:
            img_float = image.copy()
            
        if img_float.ndim == 2:
            img_float = np.stack([img_float]*3, axis=-1)
        elif img_float.ndim == 3 and img_float.shape[2] == 1:
            img_float = np.concatenate([img_float]*3, axis=-1)
            
        alpha_exp = alpha[..., np.newaxis]
        result = img_float * (1.0 - alpha_exp) + rgb_ov * alpha_exp
        
        return np.clip(result, 0.0, 1.0)
