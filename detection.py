"""A module for classifying directional arrows using TensorFlow."""

import utils
import cv2
import tensorflow as tf
import numpy as np


#########################
#       Functions       #
#########################
def load_model():
    model_dir = f'assets/models/rune_model_rnn_filtered_cannied/saved_model'
    model = tf.saved_model.load(model_dir)
    return model


def canny(image):
    image = cv2.Canny(image, 200, 300)
    colored = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return colored


def filter_color(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (1, 100, 100), (75, 255, 255))

    # Mask the image
    color_mask = mask > 0
    arrows = np.zeros_like(image, np.uint8)
    arrows[color_mask] = image[color_mask]
    return arrows


def run_inference_for_single_image(model, image):
    image = np.asarray(image)

    input_tensor = tf.convert_to_tensor(image)
    input_tensor = input_tensor[tf.newaxis,...]

    model_fn = model.signatures['serving_default']
    output_dict = model_fn(input_tensor)
    
    num_detections = int(output_dict.pop('num_detections'))
    output_dict = {key: value[0,:num_detections].numpy() 
                   for key, value in output_dict.items()}
    output_dict['num_detections'] = num_detections
    output_dict['detection_classes'] = output_dict['detection_classes'].astype(np.int64)
    return output_dict


def sort_by_confidence(model, image):
    output_dict = run_inference_for_single_image(model, image)
    zipped = list(zip(output_dict['detection_scores'], output_dict['detection_boxes'], output_dict['detection_classes']))
    pruned = [tuple for tuple in zipped if tuple[0] > 0.5]
    pruned.sort(key=lambda x: x[0], reverse=True)
    result = pruned[:4]
    return result


def get_boxes(image):
    output_dict = run_inference_for_single_image(detection_model, image)
    zipped = list(zip(output_dict['detection_scores'], output_dict['detection_boxes'], output_dict['detection_classes']))
    pruned = [tuple for tuple in zipped if tuple[0] > 0.5]
    pruned.sort(key=lambda x: x[0], reverse=True)
    pruned = pruned[:4]
    boxes = [tuple[1:] for tuple in pruned]
    return boxes


@utils.run_if_enabled
def merge_detection(image):
    label_map = {1: 'up', 2: 'down', 3: 'left', 4: 'right'}
    converter = {'up': 'right', 'down': 'left'}
    classes = []
    
    # Preprocessing
    height, width, channels = image.shape
    cropped = image[120:height//2, width//4:3*width//4]
    filtered = filter_color(cropped)
    cannied = canny(filtered)

    # Isolate the rune box
    height, width, channels = cannied.shape
    boxes = get_boxes(cannied)
    if len(boxes) == 4:           # Only run further inferences if arrows have been correctly detected
        y_mins = [b[0][0] for b in boxes]
        x_mins = [b[0][1] for b in boxes]
        y_maxes = [b[0][2] for b in boxes]
        x_maxes = [b[0][3] for b in boxes]
        left = int(round(min(x_mins) * width))
        right = int(round(max(x_maxes) * width))
        top = int(round(min(y_mins) * height))
        bottom = int(round(max(y_maxes) * height))
        rune_box = cannied[top:bottom, left:right]

        # Pad the rune box with black borders, effectively eliminating the noise around it
        height, width, channels = rune_box.shape
        pad_height, pad_width = 384, 455
        preprocessed = np.full((pad_height, pad_width, channels), (0, 0, 0), dtype=np.uint8)
        x_offset = (pad_width - width) // 2
        y_offset = (pad_height - height) // 2

        if x_offset > 0 and y_offset > 0:
            preprocessed[y_offset:y_offset+height, x_offset:x_offset+width] = rune_box

        # Run detection on preprocessed image
        lst = sort_by_confidence(detection_model, preprocessed)
        lst.sort(key=lambda x: x[1][1])
        classes = [label_map[item[2]] for item in lst]

        # Run detection on rotated image
        rotated = cv2.rotate(preprocessed, cv2.ROTATE_90_COUNTERCLOCKWISE)
        lst = sort_by_confidence(detection_model, rotated)
        lst.sort(key=lambda x: x[1][2], reverse=True)
        rotated_classes = [converter[label_map[item[2]]]
                           for item in lst
                           if item[2] in [1, 2]]
            
        # Merge the two detection results
        for i in range(len(classes)):
            if rotated_classes and classes[i] in ['left', 'right']:
                classes[i] = rotated_classes.pop(0)

    return classes


#############################
#       Initialization      #
#############################
detection_model = load_model()

# Run the inference once to 'warm up' tensorflow (the first detection triggers a long setup process)
test_image = cv2.imread('assets/inference_test_image.jpg')
merge_detection(test_image)
utils.print_separator()
print('Initialized detection algorithm.\n')

# Script for testing only the detection module
if __name__ == '__main__':
    import mss
    monitor = {'top': 0, 'left': 0, 'width': 1366, 'height': 768}
    while True:
        with mss.mss() as sct:
            frame = np.array(sct.grab(monitor))
            cv2.imshow('frame', canny(filter_color(frame)))
            arrows = merge_detection(frame)
            print(arrows)
            if cv2.waitKey(1) & 0xFF == 27:     # 27 is ASCII for the Esc key
                break
