import cv2
import os

def validate_image(image_path):
    # 1. Check if the file exists on disk
    if not os.path.exists(image_path):
        print(f"Validation Failed: File does not exist at {image_path}")
        return False

    # 2. Attempt to read the image
    # Returns None if the file is corrupted, empty, or an unsupported format
    image = cv2.imread(image_path)

    if image is None:
        print("Validation Failed: File is corrupted or not a supported image format.")
        return False

    # 3. Check for valid dimensions (height, width, channels)
    # Empty images can sometimes resolve to a shape structure of 0s
    if image.size == 0 or image.shape[0] == 0 or image.shape[1] == 0:
        print("Validation Failed: Image has zero width or height.")
        return False

    print(f"Validation Success! Dimensions: {image.shape} (HxWxC) | Data Type: {image.dtype}")
    return True