import cv2
from core import detector
from core import image_processor as processor
from coreUI import slider_widget as slider
from utils import processing_utils as utils
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSlot, QDir
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QFileDialog, QMainWindow, QDesktopWidget
from PyQt5.uic import loadUi


# UI form
MAIN_WINDOW_UI = 'coreUI/main_window.ui'

# String definitions
BEHAVIOR_FILTER = "Filter:"
BEHAVIOR_BRIGHTNESS = "Brightness"
BEHAVIOR_CONTRAST = "Contrast"
BEHAVIOR_ROTATION = "Rotation"

# ComboBox options
HIDE_FACIAL_RECOG = 0
SHOW_FACIAL_RECOG = 1


class MainWindow(QMainWindow):
    """Main UI window"""

    def __init__(self):
        super(MainWindow, self).__init__()
        loadUi(MAIN_WINDOW_UI, self)

        # Center the window on launch
        self.center()
        
        # Top menu bar options
        self.menuBar().addMenu("&Webcam Options").addAction("&Enable")
        self.menuBar().addMenu("&Image Options").addAction("&Description")

        # Facial recognition: Face/eyes detector
        self._detector = detector.Detector()

        # Filtering Kernels
        self._kernels = utils.Kernels()

        # Cached images
        self._color_img = None              # Colored image
        self._grayscale_img = None          # Grayscale image
        self._processed_img = None          # Processed image
        self._rotated_img = None            # Rotated image
        self._detected_img = None           # Detected image

        # Initially create a filter processing behavior, passing it the list of kernel names
        fp_behavior = utils.ProcessingBehavior((
            0, len(self._kernels.kernels_list) - 1), BEHAVIOR_FILTER, 0)
        fp_behavior.setting_info = [k_n for (k_n, _) in self._kernels.kernels_list]

        # Maps behaviors to their respective ImageProcessor
        self._processors = {
            BEHAVIOR_BRIGHTNESS: processor.BrightnessProcessor(utils.ProcessingBehavior(
                (-50, 50), BEHAVIOR_BRIGHTNESS, 0)),
            BEHAVIOR_CONTRAST: processor.ContrastProcessor(utils.ProcessingBehavior(
                (-50, 50), BEHAVIOR_CONTRAST, 0)),
            BEHAVIOR_FILTER: processor.FilterProcessor(fp_behavior)
        }

        # Rotation behavior will be used independent of the sliders, since rotation uses a QDial/QSpinBox
        rotation_behavior = utils.ProcessingBehavior(
            (self.rotateImgDial.minimum(), self.rotateImgDial.maximum()), BEHAVIOR_ROTATION, 0)
        self._rotation_processor = processor.RotationProcessor(rotation_behavior)

        self.create_sliders()

        self.importButton.clicked.connect(self.on_import_clicked)
        self.saveButton.clicked.connect(self.on_save_clicked)
        self.facialRecogComboBox.currentIndexChanged.connect(self.on_facial_recog_cb_changed)

        # Image rotation connection loops
        # SpinBox and the dial are connected to each other's setters, along with each being able to
        # call rotate_image simultaneously
        self.rotateImgDial.valueChanged.connect(self.rotate_image)
        self.rotateImgSpinBox.valueChanged.connect(self.rotate_image)
        self.rotateImgDial.valueChanged.connect(self.rotateImgSpinBox.setValue)
        self.rotateImgSpinBox.valueChanged.connect(self.rotateImgDial.setValue)

    def create_sliders(self):
        """
        Creates a slider for each processing behavior, and connects each of the sliders to a widget
        container. The widget will emit a signal every time it's slider is moved
        :return:
        """
        for (_, v) in self._processors.items():
            widget = slider.SliderWidget(v.behavior())
            widget.slider_moved.connect(self.on_slider_move)
            self.sliderLayout.addWidget(widget)

    def center(self):
        """
        Move the UI location to the center of the screen
        :return:
        """
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def on_slider_move(self, behavior_name, slider_value):
        """
        Slot which catches emitted slider movements
        :param behavior_name: Processor behavior.name
        :param slider_value: QSlider value from the UI
        """
        if self._color_img is None:
            return

        # Cache the processors unique value from it's respective slider position
        self._processors[behavior_name].set_unique_value(slider_value)

        # We need to loop through every processor and reprocess each time any slider is moved
        for (_, p) in self._processors.items():
            # Use the rotated image for any changed dimensions
            self._processed_img = p.process_image(self._rotated_img, self._processed_img)

        self.display_img(self._processed_img, self.rightImgLabel)

    def rotate_image(self, rotation_angle):
        """
        Handle when an image is rotated via the dial or spinbox
        :param rotation_angle: Angle of rotation from the QDial
        :return:
        """
        if self._color_img is None:
            return

        self._rotation_processor.set_unique_value(rotation_angle)
        self._rotated_img = self._rotation_processor.process_image(self._color_img, self._processed_img)

        # Do processing every time the image is rotated, this time used the processed image in place of the
        # un-modified image. We want to use the size/shape of the transformed image this time
        for (_, p) in self._processors.items():
            self._processed_img = p.process_image(self._rotated_img, self._processed_img)

        self.display_img(self._processed_img, self.rightImgLabel)

    def on_facial_recog_cb_changed(self, cb_index):
        """
        Handle when the detect button is clicked on the UI
        """
        if self._color_img is None:
            return

        if cb_index == SHOW_FACIAL_RECOG:
            self.display_img(self._detected_img, self.leftImgLabel)
        if cb_index == HIDE_FACIAL_RECOG:
            self.display_img(self._color_img, self.leftImgLabel)

    def display_detection(self):
        """
        Display results after detection
        :return:
        """
        num_faces = self._detector.faces()
        if num_faces == 1:
            self.imgDescriptLabel.setText("There is one face detected in the imported photo.")
        elif num_faces > 1:
            self.imgDescriptLabel.setText(f"There are {num_faces} faces detected in the imported photo.")
        else:
            self.imgDescriptLabel.setText("No faces detected in imported photo.")

    @pyqtSlot()
    def on_import_clicked(self):
        """
        Handle when the import button is clicked on the UI
        :return:
        """
        (filename, _) = QFileDialog.getOpenFileName(self, 'Open File', QDir.home().path(), "Image Files (*.jpg)")
        if filename:
            self.load_image(filename)

    @pyqtSlot()
    def on_save_clicked(self):
        """
        Handle when the save button is clicked on the UI
        :return:
        """
        (filename, _) = QFileDialog.getSaveFileName(self, 'Save File', QDir.home().path(), "Image Files (*.jpg)")
        if filename:
            cv2.imwrite(filename, self._processed_img)

    @pyqtSlot()
    def on_exit_button_clicked(self):
        """
        Handle when the exit button is clicked on the UI
        :return:
        """
        self.close()

    def load_image(self, img_path):
        """
        Loads an image
        :param img_path: The path to (including) the image
        :return: Return nothing if the image is not found
        """
        self._color_img = cv2.imread(img_path)
        if self._color_img is None:
            return

        self._grayscale_img = cv2.cvtColor(self._color_img, cv2.COLOR_BGR2GRAY)
        self._processed_img = self._color_img.copy()
        self._rotated_img = self._color_img.copy()
        self._detected_img = self._color_img.copy()

        # Try to detect faces on import
        self._detected_img = self._detector.detect(self._grayscale_img, self._detected_img)
        self.display_detection()

        if self.facialRecogComboBox.currentIndex() == SHOW_FACIAL_RECOG:
            self.display_img(self._detected_img, self.leftImgLabel)
        else:
            self.display_img(self._color_img, self.leftImgLabel)

        # Display the original image on the right label on import
        self.display_img(self._color_img, self.rightImgLabel)

    @staticmethod
    def display_img(image, image_label):
        """
        Display an image on a given image label
        :param image: The image to display (from openCV)
        :param image_label: The QLabel to display the image on
        :return:
        """
        # Ensure the proper image format before storing as a QImage
        q_format = QImage.Format_Indexed8

        if len(image.shape) == 3:  # rows[0], cols[1], channels[2]
            if image.shape[2] == 4:
                q_format = QImage.Format_RGBA8888
            else:
                q_format = QImage.Format_RGB888

        (h, w) = image.shape[:2]
        q_image = QImage(image, w, h, image.strides[0], q_format)
        q_image = q_image.scaled(500, 500, QtCore.Qt.KeepAspectRatio)

        # Since openCV loads an image as BGR, we need to convert from BGR -> RBG
        img = q_image.rgbSwapped()

        # Resize the label to the scaled images width and height
        image_label.resize(img.rect().width(), img.rect().height())
        image_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
        # Set the image -> pixmap -> label
        image_label.setPixmap(QPixmap.fromImage(img))
