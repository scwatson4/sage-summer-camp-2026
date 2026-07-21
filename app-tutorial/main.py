import argparse
import numpy as np
import cv2
from waggle.plugin import Plugin
from waggle.data.vision import Camera


def compute_mean_color(image):
    return np.mean(image, (0, 1)).astype(float)


def compute_min_color(image):
    return np.min(image, (0, 1)).astype(float)


def compute_max_color(image):
    return np.max(image, (0, 1)).astype(float)


def grab_image(source):
    """Return an RGB image and timestamp from a camera URL or local image file."""
    if source.startswith(("rtsp://", "rtsps://", "http://", "https://")):
        snapshot = Camera(source).snapshot()
        return snapshot.data, snapshot.timestamp
    return cv2.cvtColor(cv2.imread(source), cv2.COLOR_BGR2RGB), None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="example.jpg",
        help="image file or camera stream URL (e.g. rtsp://...)",
    )
    args = parser.parse_args()

    with Plugin() as plugin:
        image, timestamp = grab_image(args.input)

        # compute mean, min, and max color
        mean_color = compute_mean_color(image)
        min_color = compute_min_color(image)
        max_color = compute_max_color(image)

        # publish mean color
        plugin.publish("color.mean.r", mean_color[0], timestamp=timestamp)
        plugin.publish("color.mean.g", mean_color[1], timestamp=timestamp)
        plugin.publish("color.mean.b", mean_color[2], timestamp=timestamp)

        # publish min color
        plugin.publish("color.min.r", min_color[0], timestamp=timestamp)
        plugin.publish("color.min.g", min_color[1], timestamp=timestamp)
        plugin.publish("color.min.b", min_color[2], timestamp=timestamp)

        # publish max color
        plugin.publish("color.max.r", max_color[0], timestamp=timestamp)
        plugin.publish("color.max.g", max_color[1], timestamp=timestamp)
        plugin.publish("color.max.b", max_color[2], timestamp=timestamp)

        # save a copy and upload it
        cv2.imwrite("snapshot.jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        plugin.upload_file("snapshot.jpg", timestamp=timestamp)


if __name__ == "__main__":
    main()
