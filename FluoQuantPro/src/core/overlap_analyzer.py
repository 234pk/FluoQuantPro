import cv2
import numpy as np
from typing import List, Tuple, Dict
from PySide6.QtGui import QPainterPath

from src.core.analysis import MeasureEngine
from src.core.data_model import ImageChannel
from src.core.roi_model import ROI

class ROIOverlapAnalyzer:
    """
    Non-intrusive analyzer for calculating geometric overlap between two ROIs.
    Does not modify existing ROI classes.
    """
    
    @staticmethod
    def calculate_overlap(roi1_data: dict, roi2_data: dict, channels: List[ImageChannel] = None, pixel_size: float = 1.0) -> Dict:
        """
        Calculates overlap metrics between two ROIs.
        
        Args:
            roi1_data: Dict containing 'id', 'path' (QPainterPath), 'area' (optional)
            roi2_data: Dict containing 'id', 'path' (QPainterPath), 'area' (optional)
            channels: List of ImageChannel objects for intensity stats calculation.
            pixel_size: Physical size of one pixel.
            
        Returns:
            Dict containing:
            - overlap_area
            - iou (Intersection over Union)
            - overlap_ratio (relative to smaller ROI)
            - centroid (x, y)
            - intersection_stats: Dict of intensity stats for intersection area
            - area1_only_stats: Dict of intensity stats for area1 only
            - area2_only_stats: Dict of intensity stats for area2 only
        """
        path1 = roi1_data['path']
        path2 = roi2_data['path']
        
        # Calculate Intersection
        intersection_path = path1.intersected(path2)
        
        # Calculate Difference Paths (A-B, B-A)
        path1_only = path1.subtracted(path2)
        path2_only = path2.subtracted(path1)
        
        # Calculate Areas
        # Note: QPainterPath doesn't have a direct area() method.
        # We use OpenCV for accurate polygon area calculation.
        area1 = ROIOverlapAnalyzer._calculate_path_area(path1)
        area2 = ROIOverlapAnalyzer._calculate_path_area(path2)
        overlap_area = ROIOverlapAnalyzer._calculate_path_area(intersection_path)
        
        # Calculate Metrics
        union_area = area1 + area2 - overlap_area
        iou = overlap_area / union_area if union_area > 0 else 0.0
        
        min_area = min(area1, area2)
        overlap_ratio = overlap_area / min_area if min_area > 0 else 0.0
        
        centroid = ROIOverlapAnalyzer._calculate_centroid(intersection_path)
        
        # Intensity Stats
        intersection_stats = {}
        area1_only_stats = {}
        area2_only_stats = {}
        
        if channels:
            engine = MeasureEngine()
            
            # Helper to measure path
            def measure_path(path):
                if path.isEmpty():
                    return {}
                # Create temporary ROI for measurement
                temp_roi = ROI(path=path)
                return engine.measure_roi(temp_roi, channels, pixel_size=pixel_size)
                
            intersection_stats = measure_path(intersection_path)
            area1_only_stats = measure_path(path1_only)
            area2_only_stats = measure_path(path2_only)
        
        return {
            "overlap_area": overlap_area,
            "union_area": union_area,
            "area1_only": area1 - overlap_area,
            "area2_only": area2 - overlap_area,
            "iou": iou,
            "overlap_ratio": overlap_ratio,
            "centroid": centroid,
            "label_1": roi1_data.get('label', 'A'),
            "label_2": roi2_data.get('label', 'B'),
            "label": f"Overlap({roi1_data.get('label', 'A')}, {roi2_data.get('label', 'B')})",
            "intersection_stats": intersection_stats,
            "area1_only_stats": area1_only_stats,
            "area2_only_stats": area2_only_stats
        }

    @staticmethod
    def calculate_multi_overlap(rois_data: List[dict], channels: List[ImageChannel] = None, pixel_size: float = 1.0) -> Dict:
        """
        Calculates intersection of multiple ROIs.
        
        Args:
            rois_data: List of Dicts containing 'id', 'path', 'label', 'area'.
            channels: List of ImageChannel objects.
            pixel_size: float
            
        Returns:
            Dict containing metrics for the intersection of ALL ROIs.
        """
        if not rois_data:
            return {}
            
        intersection_path = rois_data[0]['path']
        union_path = rois_data[0]['path']
        
        for i in range(1, len(rois_data)):
            intersection_path = intersection_path.intersected(rois_data[i]['path'])
            union_path = union_path.united(rois_data[i]['path'])
            
        overlap_area = ROIOverlapAnalyzer._calculate_path_area(intersection_path)
        union_area = ROIOverlapAnalyzer._calculate_path_area(union_path)
        
        centroid = ROIOverlapAnalyzer._calculate_centroid(intersection_path)
        
        intersection_stats = {}
        if channels:
            engine = MeasureEngine()
            def measure_path(path):
                if path.isEmpty(): return {}
                temp_roi = ROI(path=path)
                return engine.measure_roi(temp_roi, channels, pixel_size=pixel_size)
            intersection_stats = measure_path(intersection_path)
            
        labels = [r.get('label', '?') for r in rois_data]
        # Truncate label if too long
        if len(labels) > 3:
            label_str = f"Overlap(All {len(labels)} Selected)"
        else:
            label_str = "Overlap(" + ",".join(labels) + ")"
        
        return {
            "overlap_area": overlap_area,
            "union_area": union_area,
            "non_overlap_area": union_area - overlap_area,
            "centroid": centroid,
            "label": label_str,
            "intersection_stats": intersection_stats,
            "roi_count": len(rois_data)
        }

    @staticmethod
    def _calculate_path_area(path: QPainterPath) -> float:
        """Converts QPainterPath to polygon and calculates area using OpenCV."""
        if path.isEmpty():
            return 0.0
            
        # Convert path to polygons (handling subpaths)
        # QPainterPath can contain multiple subpaths (e.g. holes).
        # toSubpathPolygons returns list of QPolygonF
        polygons = path.toSubpathPolygons()
        
        total_area = 0.0
        for poly in polygons:
            # Convert QPolygonF to numpy array
            points = []
            for i in range(poly.count()):
                pt = poly.at(i)
                points.append([pt.x(), pt.y()])
            
            if not points:
                continue
                
            pts = np.array(points, dtype=np.float32)
            # cv2.contourArea calculates signed area, take abs
            area = abs(cv2.contourArea(pts))
            
            # Simple heuristic: Assuming non-intersecting subpaths add up.
            # (Holes handling would require checking orientation/nesting, 
            # but for simple ROI intersection, summing usually works or we assume simple polygons)
            # QPainterPath.toSubpathPolygons() usually separates disjoint parts.
            total_area += area
            
        return total_area

    @staticmethod
    def _calculate_centroid(path: QPainterPath) -> Tuple[float, float]:
        """Calculates centroid of the path."""
        if path.isEmpty():
            return (0.0, 0.0)
            
        polygons = path.toSubpathPolygons()
        if not polygons:
            return (0.0, 0.0)
            
        # Weighted centroid of all subpolygons
        total_area = 0.0
        cx_sum = 0.0
        cy_sum = 0.0
        
        for poly in polygons:
            points = []
            for i in range(poly.count()):
                pt = poly.at(i)
                points.append([pt.x(), pt.y()])
                
            if not points:
                continue
                
            pts = np.array(points, dtype=np.float32)
            M = cv2.moments(pts)
            
            if M["m00"] != 0:
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]
                area = M["m00"]
                
                cx_sum += cx * area
                cy_sum += cy * area
                total_area += area
                
        if total_area > 0:
            return (cx_sum / total_area, cy_sum / total_area)
        else:
            return (0.0, 0.0)

    @staticmethod
    def calculate_overlap_matrix(rois_data: List[dict]) -> Tuple[List[str], np.ndarray, np.ndarray]:
        """
        Calculates pairwise overlap metrics for a list of ROIs.
        
        Args:
            rois_data: List of Dicts containing 'id', 'path', 'label', 'area'.
            
        Returns:
            Tuple of (labels, iou_matrix, overlap_ratio_matrix)
            - labels: List of ROI labels
            - iou_matrix: N x N matrix of IoU values
            - overlap_ratio_matrix: N x N matrix of Overlap Ratio values
        """
        n = len(rois_data)
        labels = [r.get('label', f"ROI_{i}") for i, r in enumerate(rois_data)]
        iou_matrix = np.zeros((n, n))
        overlap_ratio_matrix = np.zeros((n, n))
        
        for i in range(n):
            for j in range(i, n): # Symmetric or diagonal
                if i == j:
                    iou_matrix[i, j] = 1.0
                    overlap_ratio_matrix[i, j] = 1.0
                    continue
                
                path1 = rois_data[i]['path']
                path2 = rois_data[j]['path']
                area1 = rois_data[i].get('area', ROIOverlapAnalyzer._calculate_path_area(path1))
                area2 = rois_data[j].get('area', ROIOverlapAnalyzer._calculate_path_area(path2))
                
                intersection = path1.intersected(path2)
                overlap_area = ROIOverlapAnalyzer._calculate_path_area(intersection)
                
                union_area = area1 + area2 - overlap_area
                iou = overlap_area / union_area if union_area > 0 else 0.0
                
                min_area = min(area1, area2)
                overlap_ratio = overlap_area / min_area if min_area > 0 else 0.0
                
                iou_matrix[i, j] = iou
                iou_matrix[j, i] = iou
                
                overlap_ratio_matrix[i, j] = overlap_ratio
                overlap_ratio_matrix[j, i] = overlap_ratio
                
        return labels, iou_matrix, overlap_ratio_matrix

    @staticmethod
    def get_overlap_mask(path1: QPainterPath, path2: QPainterPath, shape: Tuple[int, int]) -> np.ndarray:
        """Generates a binary mask for the intersection of two ROI paths."""
        intersection = path1.intersected(path2)
        from src.core.algorithms import qpath_to_mask
        return qpath_to_mask(intersection, shape)

    @staticmethod
    def get_non_overlap_boundary(path1: QPainterPath, path2: QPainterPath) -> List[Tuple[float, float]]:
        """
        Returns the boundary points of the non-overlapping parts.
        (A - B) U (B - A)
        """
        diff1 = path1.subtracted(path2)
        diff2 = path2.subtracted(path1)
        union_diff = diff1.united(diff2)
        
        # Extract points from path
        points = []
        polygons = union_diff.toSubpathPolygons()
        for poly in polygons:
            for i in range(poly.count()):
                pt = poly.at(i)
                points.append((pt.x(), pt.y()))
        return points
