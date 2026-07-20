import numpy as np
import cv2
from waggle.plugin import Plugin


def compute_mean_color(image):
    return np.mean(image, (0, 1)).astype(float)


def compute_min_color(image):
    return np.min(image, (0, 1)).astype(float)


def compute_max_color(image):
    return np.max(image, (0, 1)).astype(float)


def main():
    with Plugin() as plugin:
        # read example image from file (cv2 loads BGR, convert to RGB)
        image = cv2.cvtColor(cv2.imread("example.jpg"), cv2.COLOR_BGR2RGB)

        # compute mean, min, and max color
        mean_color = compute_mean_color(image)
        min_color = compute_min_color(image)
        max_color = compute_max_color(image)

        # publish mean color
        plugin.publish("color.mean.r", mean_color[0])
        plugin.publish("color.mean.g", mean_color[1])
        plugin.publish("color.mean.b", mean_color[2])

        # publish min color
        plugin.publish("color.min.r", min_color[0])
        plugin.publish("color.min.g", min_color[1])
        plugin.publish("color.min.b", min_color[2])

        # publish max color
        plugin.publish("color.max.r", max_color[0])
        plugin.publish("color.max.g", max_color[1])
        plugin.publish("color.max.b", max_color[2])

        # save a copy and upload it
        cv2.imwrite("snapshot.jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        plugin.upload_file("snapshot.jpg")


if __name__ == "__main__":
    main()
