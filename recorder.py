from PyQt5 import QtWidgets, QtCore, QtGui
from ui import Ui_MainWindow
from utils import get_ports
import serial
import os
import pandas as pd

LABEL_COLUMN = "label"
DONE_COLUMN = "done_count"
TOTAL_COLUMN = "total_count"


class UpdatebleCombobox(QtWidgets.QComboBox):
    clicked = QtCore.pyqtSignal()

    def showPopup(self):
        self.clicked.emit()
        super(UpdatebleCombobox, self).showPopup()


class Recorder:
    def __init__(self):
        self.ui = Ui_MainWindow()
        self.is_recording = False
        self.data = []
        self.breakpoints = [0]
        self.record_timer = QtCore.QTimer()
        self.record_timer.timeout.connect(self.showTime)
        self.recording_time = 0
        self.remaining_labels = 0
        self.csv_file = None
        self.next_labels = None
        self.current_iloc = 0
        self.serial_object = None

    def setupUi(self, main_window):
        self.ui.setupUi(main_window)
        self.ui.inputLayout.removeWidget(self.ui.SerialPortCombo)
        self.ui.SerialPortCombo.deleteLater()
        self.ui.SerialPortCombo = UpdatebleCombobox(self.ui.centralwidget)
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
        )
        sizePolicy.setHorizontalStretch(20)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.ui.SerialPortCombo.sizePolicy().hasHeightForWidth()
        )
        self.ui.SerialPortCombo.setSizePolicy(sizePolicy)
        self.ui.SerialPortCombo.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.ui.SerialPortCombo.setObjectName("SerialPortCombo")
        self.ui.inputLayout.insertWidget(1, self.ui.SerialPortCombo)

        self.ui.SerialPortCombo.addItems(get_ports())
        self.ui.SerialPortCombo.clicked.connect(self.serialPortComboClicked)

        self.ui.recorderCombo.currentTextChanged.connect(self.recorderComboClicked)

        self.ui.startButton.clicked.connect(self.startButtonPressed)

        self.ui.stopButton.clicked.connect(self.stopButtonPressed)

        self.ui.putSepButton.clicked.connect(self.putSepButtonPressed)

        self.ui.saveButton.clicked.connect(self.saveButtonPressed)

        self.ui.csvButton.clicked.connect(self.csvButtonPressed)

        self.ui.connectButton.clicked.connect(self.connectButtonPressed)

        _translate = QtCore.QCoreApplication.translate
        self.ui.timeLabel.setText(_translate("MainWindow", self.clear_time_text()))
        self.ui.startButton.setShortcut(_translate("MainWindow", "Ctrl+N"))
        self.ui.stopButton.setShortcut(_translate("MainWindow", "Ctrl+E"))
        self.ui.putSepButton.setShortcut(_translate("MainWindow", "Ctrl+P"))
        self.ui.saveButton.setShortcut(_translate("MainWindow", "Ctrl+S"))

    def connectButtonPressed(self):
        port = self.ui.SerialPortCombo.currentText()
        baudrate = 9600
        try:
            self.serial_object = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=8,
                timeout=2,
                stopbits=serial.STOPBITS_ONE,
            )
            self.ui.connectButton.setEnabled(False)
        except Exception as e:
            self.error.emit("Could not open serial port!", "Error!")
            self.serial_object = None

        if self.csv_file and self.serial_object:
            self.schedule_recording(self.csv_file)

    def serialPortComboClicked(self):
        self.ui.SerialPortCombo.clear()
        self.ui.SerialPortCombo.addItems(get_ports())

    def recorderComboClicked(self, name):
        if self.csv_file is not None and self.serial_object is not None:
            self.schedule_recording(self.csv_file)

    def clear_time_text(self):
        return "Record Time: 00:00"

    def showTime(self):
        self.recording_time += 1
        minutes = str(self.recording_time // 60).zfill(2)
        seconds = str(self.recording_time % 60).zfill(2)
        self.ui.timeLabel.setText(f"Record Time: {minutes}:{seconds}")

    def startButtonPressed(self):
        if self.csv_file is None:
            return self.on_error(
                "Please choose a CSV file before recording.", "CSV file error"
            )

        if self.current_iloc >= len(self.next_labels):
            return self.on_error(
                "The current csv file is finished. Please choose another file.",
                "CSV finished error",
            )

        self.is_recording = True
        self.ui.startButton.setEnabled(False)  # disable start button
        self.ui.stopButton.setEnabled(True)  # enable stop button
        self.ui.putSepButton.setEnabled(True)  # enable put seperator button
        self.ui.textEdit.clear()  # clear textedit
        self.ui.timeLabel.setText(self.clear_time_text())  # clear time label
        self.record_timer.start(1000)

        self.serial_object.flush()
        self.worker = self.DataTransferHandlerThread(outer_class=self)

        self.worker.error.connect(self.on_error)
        self.worker.data.connect(self.on_data)
        self.worker.start()

    def stopButtonPressed(self):
        self.record_timer.stop()
        self.is_recording = False
        self.worker.terminate()
        self.recording_time = 0
        self.ui.startButton.setEnabled(True)
        self.ui.stopButton.setEnabled(False)
        self.ui.putSepButton.setEnabled(False)
        self.ui.saveButton.setEnabled(True)

        # show data in textedit
        breakpoint_index = 1
        self.ui.textEdit.clear()
        for i, data in enumerate(self.data):
            if (
                breakpoint_index < len(self.breakpoints)
                and i == self.breakpoints[breakpoint_index]
            ):
                self.ui.textEdit.appendPlainText(self.ui.seperatorLineEdit.text())
                breakpoint_index += 1
            self.ui.textEdit.appendPlainText(data[:-2])

    def putSepButtonPressed(self):
        if self.breakpoints[-1] != len(self.data):
            self.breakpoints.append(len(self.data))

    def saveButtonPressed(self):
        # TODO: check and set output format
        # check if label is not specified
        # if self.ui.labelLineEdit.text() == '':
        #     return self.on_error('Please choose a label for this sample!', 'Error!')
        # getting output path
        dir = QtWidgets.QFileDialog.getExistingDirectory(caption="Select the folder")
        if dir is None or dir == "":
            return
        name = self.next_labels.iloc[self.current_iloc][LABEL_COLUMN]
        # Create output folder
        recorder_person = self.ui.recorderCombo.currentText()
        path = f"{dir}/{recorder_person}/{name}.txt"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # save file
        with open(path, "a") as f:
            for i in range(2, len(self.breakpoints)):
                for j in range(self.breakpoints[i - 1], self.breakpoints[i]):
                    # print(self.data[j])
                    sample = self.data[j][8:-2] + "\n"
                    f.write(sample)
                f.write(self.ui.seperatorLineEdit.text() + "\n")
        # add number of recorded items to csv
        done_column = f"{recorder_person}_{DONE_COLUMN}"
        total_column = f"{recorder_person}_{TOTAL_COLUMN}"
        new_data_count = len(self.breakpoints) - 2
        # print(self.csv_file)
        # print(done_column)
        prev_value = self.csv_file.loc[self.current_loc, done_column]
        self.csv_file.loc[self.current_loc, done_column] = prev_value + new_data_count
        self.csv_file.to_csv(self.csv_file_path, index=False)
        # if the current word is done increament iloc and check if the csv file is done
        if (
            self.csv_file.loc[self.current_loc][done_column]
            >= self.csv_file.loc[self.current_loc][total_column]
        ):
            self.current_iloc += 1
            self.remaining_labels -= 1
            if self.current_iloc > len(self.next_labels):
                self.setCsvLabel(
                    "The current CSV file is finished. Choose another file."
                )
            else:
                next_row = self.next_labels.iloc[self.current_iloc]
                self.current_loc = next_row[0]
                self.setCsvLabel(
                    next_row[LABEL_COLUMN],
                    next_row[done_column],
                    next_row[total_column],
                )
        else:
            # if the current word is not done update the label
            current_row = self.csv_file.loc[self.current_loc]
            self.setCsvLabel(
                current_row[LABEL_COLUMN],
                current_row[done_column],
                current_row[total_column],
            )

    def setCsvLabel(self, text):
        self.ui.csvLabel.setText(text)

    def setCsvLabel(self, label, done_count, total_count):
        self.ui.csvLabel.setText(
            f"Next label: {label} ({done_count}/{total_count}) Rem: {self.remaining_labels}"
        )

    def csvButtonPressed(self):
        self.ui.startButton.setEnabled(False)
        # Get file name
        self.csv_file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            caption="Select the CSV file",
            directory="../data_planner/foldedData",
        )
        # Raise error if no file is selected
        if not self.csv_file_path:
            return
        # Raise error if the file is not a CSV file
        if not self.csv_file_path.lower().endswith(".csv"):
            return self.on_error(
                "The selected file is not a CSV file. The file name must end with .csv extension",
                "CSV file error!",
            )
        # Read CSV file and the next label
        prev_csv_file = self.csv_file
        self.csv_file = pd.read_csv(self.csv_file_path)
        self.schedule_recording(prev_csv_file)
        self.ui.startButton.setEnabled(True)

    def schedule_recording(self, on_error_csv_file):
        recorder_person = self.ui.recorderCombo.currentText()
        done_column = f"{recorder_person}_{DONE_COLUMN}"
        total_column = f"{recorder_person}_{TOTAL_COLUMN}"
        # raise error if the columns are not valid
        if not {LABEL_COLUMN, done_column, total_column}.issubset(
            set(self.csv_file.columns)
        ):
            self.csv_file = on_error_csv_file
            return self.on_error(
                "The CSV file columns are not valid!", "CSV columns error"
            )
        # Get not done rows
        self.next_labels = self.csv_file[
            self.csv_file[done_column] < self.csv_file[total_column]
        ]
        self.remaining_labels = len(self.next_labels)
        # raise error if the csv file is finished
        if len(self.next_labels) == 0:
            self.csv_file = on_error_csv_file
            return self.on_error(
                "The chosen CSV file is finished. Please choose another file!",
                "CSV finished error",
            )
        # update parameters
        self.current_iloc = 0
        next_row = self.next_labels.iloc[self.current_iloc]
        self.current_loc = next_row[0]
        # Change button and label name
        file_name = self.csv_file_path.split("/")[-1]
        self.ui.csvButton.setText(f"Change CSV file (Current: {file_name})")
        self.setCsvLabel(
            next_row[LABEL_COLUMN], next_row[done_column], next_row[total_column]
        )
        self.ui.startButton.setEnabled(True)
        return True

    def on_error(self, text, title):
        self.record_timer.stop()
        self.clear_time_text()
        dialog = QtWidgets.QMessageBox.critical(
            None,
            title,
            text,
            buttons=QtWidgets.QMessageBox.Ok,
        )

        self.ui.saveButton.setEnabled(self.is_recording)
        self.ui.startButton.setEnabled(self.is_recording)
        self.is_recording = False
        self.recording_time = 0
        self.ui.stopButton.setEnabled(False)
        self.ui.putSepButton.setEnabled(False)
        self.ui.saveButton.setEnabled(True)

    def on_data(self, data):
        self.ui.textEdit.appendPlainText(data)

    class DataTransferHandlerThread(QtCore.QThread):
        """
        This class is a QRunnable object that will be used to transfer data from the serial port to the text edit.
        """

        error = QtCore.pyqtSignal(str, str)
        data = QtCore.pyqtSignal(str)

        def __init__(self, outer_class) -> None:
            super().__init__()
            self.outer_class = outer_class

        @QtCore.pyqtSlot()
        def run(self):
            self.outer_class.data = []
            self.outer_class.breakpoints = [0]
            try:
                while self.outer_class.is_recording:
                    # Wait until there is data waiting in the serial buffer
                    if self.outer_class.serial_object.in_waiting > 0:
                        # Read data out of the buffer until a carraige return / new line is found
                        serialString = self.outer_class.serial_object.readline().decode(
                            "Ascii", errors="ignore"
                        )
                        # Append the data to the list
                        self.outer_class.data.append(serialString)
                        self.data.emit(serialString)

            except UnicodeDecodeError as e:
                self.outer_class.serial_object.close()
                self.outer_class.serial_object = None
                self.outer_class.ui.startButton.setEnabled(False)
                self.outer_class.ui.connectButton.setEnabled(True)
                self.error.emit(
                    "Decode error! This error is probably caused by incorrect baudrate.",
                    "Error!",
                )
                print(e)

            except Exception as e:
                self.outer_class.serial_object.close()
                self.outer_class.serial_object = None
                self.outer_class.ui.startButton.setEnabled(False)
                self.outer_class.ui.connectButton.setEnabled(True)
                self.error.emit(str(e), "Error!")


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Recorder()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())
