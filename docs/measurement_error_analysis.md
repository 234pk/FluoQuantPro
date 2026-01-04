# Measurement Error Analysis & Calibration Guide

## 1. Sources of Measurement Error

### 1.1 Pixel Size Calibration
- **Issue**: Default pixel size (1.0 um/px) may not match physical reality.
- **Impact**: Area and length measurements will be incorrect by a linear factor.
- **Solution**: Use the **Set Scale** feature (Analysis -> Set Scale) with a stage micrometer to calibrate.
- **Precision Goal**: ±0.5% (Achievable with careful calibration).

### 1.2 Background Noise
- **Issue**: Fluorescence images contain background signal (autofluorescence, sensor noise).
- **Impact**: Intensity measurements (Mean, IntDen) will be inflated.
- **Solution**: 
  - Use **Background Subtraction** (Measurement Settings).
  - Recommended: **Local Ring** subtraction for heterogeneous background.
  - Optional: **Global Min** for uniform background.

### 1.3 ROI Overlap
- **Issue**: Overlapping ROIs may double-count signals or obscure relationships.
- **Impact**: Incorrect total area or intensity if not accounted for.
- **Solution**: Use the new **ROI Overlap Analysis** feature.
  - Select exactly two ROIs.
  - View Overlap Area, IoU, and Overlap Ratio in the Measurement Results table.

### 1.4 Bit Depth Precision
- **Issue**: Converting 16-bit raw data to 8-bit for display loses information.
- **Solution**: FluoQuant Pro always measures on **Raw 16-bit Data**, regardless of display settings.
- **Verification**: Check "Min/Max" columns in results; they should reflect 0-65535 range.

## 2. Validation & Review Workflow

### 2.1 Manual Review
- Users can now mark measurement rows as **Verified** or **Rejected**.
- Right-click on a result row -> "Mark as Verified" (Green) or "Mark as Rejected" (Red).
- Rejected rows can be filtered out during export (future feature) or manually deleted.

### 2.2 Calibration Procedure
1. Open an image of a stage micrometer.
2. Draw a straight line (Line Scan tool) over a known distance (e.g., 100 um).
3. Go to **Analysis -> Set Scale...**.
4. Enter "100" in "Known Distance" and "um" in "Unit".
5. Click OK. The scale is now applied to all measurements in the session.
