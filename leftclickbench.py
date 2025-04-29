import dataclasses
import hashlib
import itertools
import math
import os
from typing import Tuple

from PIL import Image, ImageDraw

# --- Constants based on README ---

SHAPES = {"C": "circle", "R": "rectangle"}
COLORS = {
    "R": "red",
    "B": "blue",
    "G": "green",
    "Y": "yellow",
    "K": "almost_black",
    "W": "almost_white",
}
SIZES_PERCENT = {
    "1": 1,
    "2": 2,
    "4": 4,
    "8": 8,
    "S": 16,
    "T": 32,
}  # Percentage of image area
BACKGROUNDS = {"W": "white", "G": "gray", "K": "black", "F": "full_color", "B": "grid"}
IMAGE_SIZES = {
    "S": (1024, 768),  # Standard 4:3
    "M": (1280, 1024),  # Medium 5:4
    "P": (1080, 1920),  # Portrait 9:16
    "O": (101, 819),  # Odd aspect ratio
}

# Reverse lookups for encoding
SHAPE_CODES = {v: k for k, v in SHAPES.items()}
COLOR_CODES = {v: k for k, v in COLORS.items()}
SIZE_CODES = {v: k for k, v in SIZES_PERCENT.items()}
BACKGROUND_CODES = {v: k for k, v in BACKGROUNDS.items()}
IMAGE_SIZE_CODES = {v: k for k, v in IMAGE_SIZES.items()}


# --- Data Structure ---


@dataclasses.dataclass(frozen=True)
class ClickBenchTask:
    """Represents a parsed ClickBench task."""

    shape: str
    color: str
    size_percent: int
    background: str
    image_size: Tuple[int, int]
    ref_x_percent: int
    ref_y_percent: int

    @staticmethod
    def from_string(task_id: str) -> "ClickBenchTask":
        """Parses a task ID string into a ClickBenchTask object."""
        try:
            prefix, params_str, pos_str = task_id.split("_")
            if prefix != "cb1":
                raise ValueError("Invalid task ID prefix")

            if len(params_str) != 5:
                raise ValueError("Invalid parameter string length")
            if len(pos_str) != 4:
                raise ValueError("Invalid position string length")

            shape_code = params_str[0]
            color_code = params_str[1]
            size_code = params_str[2]
            bg_code = params_str[3]
            img_size_code = params_str[4]

            x_percent = int(pos_str[0:2])
            y_percent = int(pos_str[2:4])

            if not (0 <= x_percent <= 99 and 0 <= y_percent <= 99):
                raise ValueError("Position percentages out of range 00-99")

            return ClickBenchTask(
                shape=SHAPES[shape_code],
                color=COLORS[color_code],
                size_percent=SIZES_PERCENT[size_code],
                background=BACKGROUNDS[bg_code],
                image_size=IMAGE_SIZES[img_size_code],
                ref_x_percent=x_percent,
                ref_y_percent=y_percent,
            )
        except (KeyError, ValueError, IndexError, TypeError) as e:
            raise ValueError(f"Invalid task ID format: {task_id} ({e})") from e

    def to_string(self) -> str:
        """Converts the ClickBenchTask object back to its string representation."""
        try:
            shape_code = SHAPE_CODES[self.shape]
            color_code = COLOR_CODES[self.color]
            size_code = SIZE_CODES[self.size_percent]
            bg_code = BACKGROUND_CODES[self.background]
            img_size_code = IMAGE_SIZE_CODES[self.image_size]
        except KeyError as e:
            raise ValueError(f"Could not encode task parameter: {e}") from e

        params_str = f"{shape_code}{color_code}{size_code}{bg_code}{img_size_code}"
        pos_str = f"{self.ref_x_percent:02d}{self.ref_y_percent:02d}"

        return f"cb1_{params_str}_{pos_str}"


# --- Dataset Generation ---


def get_dataset():
    """
    Generates ClickBench task IDs based on the README specification,
    with one deterministically generated reference point per base parameter combination.

    Yields:
        str: A ClickBench task ID string in the format 'cb1_ShapeColorSizeBackgroundImagesize_XxYy'.
    """
    base_codes = itertools.product(
        SHAPES.keys(),
        COLORS.keys(),
        SIZES_PERCENT.keys(),
        BACKGROUNDS.keys(),
        IMAGE_SIZES.keys(),
    )

    for shape_code, color_code, size_code, bg_code, img_size_code in base_codes:
        base_id_part = f"{shape_code}{color_code}{size_code}{bg_code}{img_size_code}"
        base_id_bytes = base_id_part.encode("utf-8")

        # Generate X coordinate from hash
        hash_x = hashlib.sha256(base_id_bytes).digest()
        x_int = int.from_bytes(hash_x, "big")
        x_percent = x_int % 100  # Map to 0-99

        # Generate Y coordinate from hash (using a slightly modified input for diversity)
        hash_y = hashlib.sha256(base_id_bytes + b"_Y").digest()
        y_int = int.from_bytes(hash_y, "big")
        y_percent = y_int % 100  # Map to 0-99

        pos_part = f"{x_percent:02d}{y_percent:02d}"
        yield f"cb1_{base_id_part}_{pos_part}"


# --- Correctness Check ---


def is_correct(task_id: str, click: tuple[int, int]) -> bool:
    """
    Checks if a click falls within the target area for a given ClickBench task ID.

    Args:
        task_id: The ClickBench task ID string (e.g., 'cb1_CR1WS_2575').
        click: A tuple (x, y) representing the click coordinates.

    Returns:
        bool: True if the click is within the target, False otherwise.

    Raises:
        ValueError: If the task_id format is invalid.
    """
    task = ClickBenchTask.from_string(task_id)
    img_width, img_height = task.image_size
    click_x, click_y = click

    # Calculate reference point in pixels
    ref_x = (task.ref_x_percent / 100.0) * img_width
    ref_y = (task.ref_y_percent / 100.0) * img_height

    # Calculate target area in pixels
    target_area_pixels = (task.size_percent / 100.0) * img_width * img_height

    if task.shape == "circle":
        # Reference point is the center
        center_x, center_y = ref_x, ref_y
        # Avoid division by zero if area is zero
        radius_sq = target_area_pixels / math.pi if target_area_pixels > 0 else 0
        # Check distance squared to avoid sqrt
        distance_sq = (click_x - center_x) ** 2 + (click_y - center_y) ** 2
        return distance_sq <= radius_sq

    elif task.shape == "rectangle":
        # Reference point is top-left corner
        top_left_x, top_left_y = ref_x, ref_y
        # Avoid sqrt of negative if area is zero, though unlikely with positive size %
        side_length = math.sqrt(target_area_pixels) if target_area_pixels > 0 else 0
        bottom_right_x = top_left_x + side_length
        bottom_right_y = top_left_y + side_length

        # Check if click is within bounds (inclusive left/top, exclusive right/bottom)
        # Note: Pixel coordinates are often treated as discrete. A click at (x, y)
        # usually refers to the pixel at that integer coordinate.
        # The bounds calculated might be floats. Standard practice often involves
        # checking if integer click coords fall within the float bounds.
        return (
            top_left_x <= click_x < bottom_right_x
            and top_left_y <= click_y < bottom_right_y
        )
    else:
        # Should not happen due to parsing
        raise ValueError(f"Unknown shape: {task.shape}")


# --- Image Rendering ---

# Define actual RGB colors (adjust 'almost' colors if needed)
RGB_COLORS = {
    "red": (255, 0, 0),
    "blue": (0, 0, 255),
    "green": (0, 255, 0),
    "yellow": (255, 255, 0),
    "almost_black": (1, 1, 1),
    "almost_white": (254, 254, 254),
    "white": (255, 255, 255),
    "gray": (128, 128, 128),
    "black": (0, 0, 0),
}


def render_image(task: ClickBenchTask) -> Image.Image:
    """
    Renders the image for a given ClickBench task.

    Args:
        task: The ClickBenchTask object.

    Returns:
        A PIL Image object representing the task.
    """
    img_width, img_height = task.image_size
    bg_color_name = task.background

    # 1. Create background
    if bg_color_name == "white":
        bg = Image.new("RGB", task.image_size, RGB_COLORS["white"])
        draw = ImageDraw.Draw(bg)
    elif bg_color_name == "gray":
        bg = Image.new("RGB", task.image_size, RGB_COLORS["gray"])
        draw = ImageDraw.Draw(bg)
    elif bg_color_name == "black":
        bg = Image.new("RGB", task.image_size, RGB_COLORS["black"])
        draw = ImageDraw.Draw(bg)
    elif bg_color_name == "grid":
        bg = Image.new("RGB", task.image_size, RGB_COLORS["white"])  # Grid on white bg
        draw = ImageDraw.Draw(bg)
        grid_color = RGB_COLORS["gray"]
        grid_spacing = 50  # pixels
        for x in range(0, img_width, grid_spacing):
            draw.line([(x, 0), (x, img_height)], fill=grid_color)
        for y in range(0, img_height, grid_spacing):
            draw.line([(0, y), (img_width, y)], fill=grid_color)
    elif bg_color_name == "full_color":
        # Load the background image 'bg.jpg' from the script's directory
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            bg_path = os.path.join(script_dir, "bg.jpg")
            bg = Image.open(bg_path)
            # Resize background to match the task's image size
            bg = bg.resize(task.image_size)
            # Ensure the background image is in RGB mode
            if bg.mode != "RGB":
                bg = bg.convert("RGB")
            draw = ImageDraw.Draw(bg)
        except FileNotFoundError:
            print(
                f"Warning: Background file 'bg.jpg' not found in {script_dir}. Using gray background instead."
            )
            bg = Image.new("RGB", task.image_size, RGB_COLORS["gray"])
            draw = ImageDraw.Draw(bg)
        except Exception as e:
            print(
                f"Warning: Error loading or processing background 'bg.jpg': {e}. Using gray background instead."
            )
            bg = Image.new("RGB", task.image_size, RGB_COLORS["gray"])
            draw = ImageDraw.Draw(bg)
    else:
        # Should not happen due to parsing
        raise ValueError(f"Unknown background: {bg_color_name}")

    # 2. Calculate shape position and size
    ref_x = (task.ref_x_percent / 100.0) * img_width
    ref_y = (task.ref_y_percent / 100.0) * img_height
    target_area_pixels = (task.size_percent / 100.0) * img_width * img_height
    shape_color = RGB_COLORS[task.color]

    # 3. Draw shape
    if task.shape == "circle":
        center_x, center_y = ref_x, ref_y
        radius = (
            math.sqrt(target_area_pixels / math.pi) if target_area_pixels > 0 else 0
        )
        # Define bounding box for ellipse [x0, y0, x1, y1]
        bbox = [
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
        ]
        draw.ellipse(bbox, fill=shape_color)

    elif task.shape == "rectangle":
        top_left_x, top_left_y = ref_x, ref_y
        side_length = math.sqrt(target_area_pixels) if target_area_pixels > 0 else 0
        bottom_right_x = top_left_x + side_length
        bottom_right_y = top_left_y + side_length
        # Define bounding box for rectangle [x0, y0, x1, y1]
        bbox = [top_left_x, top_left_y, bottom_right_x, bottom_right_y]
        draw.rectangle(bbox, fill=shape_color)
    else:
        # Should not happen due to parsing
        raise ValueError(f"Unknown shape: {task.shape}")

    return bg
