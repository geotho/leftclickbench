import dataclasses
import math
import os
from pathlib import Path

import pytest

from leftclickbench import ClickBenchTask, get_dataset, is_correct, render_image


def test_dataset_generation():
    """Test that dataset generation yields valid-looking IDs."""
    gen = get_dataset()
    # Generate a few and check format loosely
    for i in range(10):
        task_id = next(gen)
        assert task_id.startswith("cb1_")
        parts = task_id.split("_")
        assert len(parts) == 3
        assert len(parts[1]) == 5  # Params
        assert len(parts[2]) == 4  # Position
        # Basic check that parsing doesn't immediately fail
        ClickBenchTask.from_string(task_id)


def test_circle_task_parsing_and_correctness():
    """Test parsing and correctness check for a circle task."""
    id1_str = "cb1_CR1WS_2575"  # Circle, Red, 1%, White, 1024x768. Center X=25%, Y=75%
    task1 = ClickBenchTask.from_string(id1_str)

    # Verify parsing
    assert task1.shape == "circle"
    assert task1.color == "red"
    assert task1.size_percent == 1
    assert task1.background == "white"
    assert task1.image_size == (1024, 768)
    assert task1.ref_x_percent == 25
    assert task1.ref_y_percent == 75

    # Verify conversion back to string
    assert task1.to_string() == id1_str

    # Verify correctness checks (based on example calculations)
    img_w1, img_h1 = task1.image_size
    center_x1 = (task1.ref_x_percent / 100.0) * img_w1  # 256
    center_y1 = (task1.ref_y_percent / 100.0) * img_h1  # 576
    area1 = (task1.size_percent / 100.0) * img_w1 * img_h1
    radius1 = math.sqrt(area1 / math.pi) if area1 > 0 else 0  # ~49.9

    assert is_correct(id1_str, (int(center_x1), int(center_y1)))  # Center
    assert is_correct(
        id1_str, (int(center_x1 + radius1 - 1), int(center_y1))
    )  # Near edge inside
    assert not is_correct(
        id1_str, (int(center_x1 + radius1 + 1), int(center_y1))
    )  # Near edge outside
    assert not is_correct(id1_str, (0, 0))  # Corner


def test_rectangle_task_parsing_and_correctness():
    """Test parsing and correctness check for a rectangle task."""
    id2_str = "cb1_RYSFM_1020"  # Rectangle, Yellow, 16%, Full color, 1280x1024. Top-left X=10%, Y=20%
    task2 = ClickBenchTask.from_string(id2_str)

    # Verify parsing
    assert task2.shape == "rectangle"
    assert task2.color == "yellow"
    assert task2.size_percent == 16
    assert task2.background == "full_color"
    assert task2.image_size == (1280, 1024)
    assert task2.ref_x_percent == 10
    assert task2.ref_y_percent == 20

    # Verify conversion back to string
    assert task2.to_string() == id2_str

    # Verify correctness checks (based on example calculations)
    img_w2, img_h2 = task2.image_size
    top_left_x2 = (task2.ref_x_percent / 100.0) * img_w2  # 128
    top_left_y2 = (task2.ref_y_percent / 100.0) * img_h2  # 204.8
    area2 = (task2.size_percent / 100.0) * img_w2 * img_h2
    side2 = math.sqrt(area2) if area2 > 0 else 0  # ~458.8
    bottom_right_x2 = top_left_x2 + side2  # ~586.8
    bottom_right_y2 = top_left_y2 + side2  # ~663.6

    assert is_correct(
        id2_str, (int(top_left_x2), math.ceil(top_left_y2))
    )  # Top-left corner (adjusting y for float)
    assert is_correct(id2_str, (200, 300))  # Inside
    assert is_correct(
        id2_str, (int(bottom_right_x2 - 1), int(bottom_right_y2 - 1))
    )  # Near bottom-right inside
    assert not is_correct(
        id2_str, (int(bottom_right_x2 + 1), int(bottom_right_y2 + 1))
    )  # Outside bottom-right
    assert not is_correct(id2_str, (0, 0))  # Corner


def test_invalid_id_parsing():
    """Test that invalid task IDs raise ValueErrors during parsing."""
    invalid_ids = [
        "invalid_id",  # Wrong prefix/format
        "cb1_CR1WS_123",  # Position too short
        "cb1_CR1WS_12345",  # Position too long
        "cb1_X_1234",  # Params too short
        "cb1_CR1WSX_1234",  # Params too long
        "cb1_XR1WS_1234",  # Invalid shape code
        "cb1_CX1WS_1234",  # Invalid color code
        "cb1_CRXWS_1234",  # Invalid size code
        "cb1_CR1XS_1234",  # Invalid background code
        "cb1_CR1WX_1234",  # Invalid image size code
        "cb1_CR1WS_10075",  # X percent > 99
        "cb1_CR1WS_25100",  # Y percent > 99
    ]
    for invalid_id in invalid_ids:
        # Use pytest.raises instead of self.assertRaises
        with pytest.raises(ValueError):
            ClickBenchTask.from_string(invalid_id)


def test_invalid_id_correctness_check():
    """Test that invalid task IDs raise ValueErrors during correctness check."""
    # This relies on from_string raising the error
    with pytest.raises(ValueError):
        is_correct("cb1_X", (10, 10))  # Invalid params string


def test_invalid_task_encoding():
    """Test that trying to encode a task with invalid parameters raises ValueError."""
    # Create a valid task first
    valid_task = ClickBenchTask.from_string("cb1_CR1WS_2575")
    # Replace a field with an invalid value (not in the reverse lookup dicts)
    invalid_task = dataclasses.replace(valid_task, shape="triangle")
    with pytest.raises(ValueError):
        invalid_task.to_string()


def test_render_image_output():
    """Test that render_image produces an image file."""
    for task_id in get_dataset():
        task = ClickBenchTask.from_string(task_id)
        if task.background == "full_color":
            break
    image = render_image(task)

    # Ensure output directory exists
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save the image
    output_path = output_dir / f"{task_id}.png"
    image.save(output_path)

    # Basic check: Did the file get created?
    assert output_path.is_file()

    # Optional: Clean up the created file (uncomment if desired)
    # os.remove(output_path)


EXPECTED_DATASET_SIZE = (
    2 * 6 * 6 * 5 * 4
)  # Shapes * Colors * Sizes * Backgrounds * Image Sizes


def test_total_dataset_size():
    """Test that the dataset generator produces the expected number of unique tasks."""
    # Calculate expected size based on parameter combinations
    # One position generated per combination.
    expected_size = EXPECTED_DATASET_SIZE  # 1440

    gen = get_dataset()
    tasks = list(gen)
    unique_tasks = set(tasks)

    assert len(tasks) == expected_size, (
        f"Expected {expected_size} tasks, but generated {len(tasks)}"
    )

    assert len(unique_tasks) == expected_size, (
        f"Expected {expected_size} unique tasks, but generated {len(unique_tasks)}"
    )


@pytest.mark.skipif(
    not os.environ.get("RUN_FULL_RENDER_TEST"),
    reason="Set RUN_FULL_RENDER_TEST=1 env var to run full image rendering",
)
def test_render_all_images():
    """Generate and save images for all tasks in the dataset."""
    output_dir = Path("output/all_images")
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_count = 0

    for task_id in get_dataset():
        task = ClickBenchTask.from_string(task_id)
        image = render_image(task)
        output_path = output_dir / f"{task_id}.png"
        image.save(output_path)
        generated_count += 1

    assert generated_count == EXPECTED_DATASET_SIZE, (
        f"Expected to generate {EXPECTED_DATASET_SIZE} images, but generated {generated_count}"
    )
    # Check if at least one file exists (basic sanity check)
    assert any(output_dir.iterdir()), "Output directory is empty after rendering."


def test_dataset_consistent():
    gen1 = get_dataset()
    gen2 = get_dataset()

    for i, (task1, task2) in enumerate(zip(gen1, gen2)):
        assert task1 == task2, f"Tasks {task1} and {task2} are different at index {i}"
