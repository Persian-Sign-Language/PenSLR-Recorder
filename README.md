# Recorder
This is a recorder GUI to record our labels. It is written in Python using PyQt5. So, you need to install PyQt5 to run this program.  

## Usage
To run the program you can simply run the following command:
```
python recorder.py
```
The program will open a window like this:  
<img src="Recorder.png" width=610 height=500/>

To edit the GUI you can use Qt Designer. The file `design.ui` is the file that Qt Designer uses to generate the GUI. You can open it with Qt Designer and edit it. Then, you can generate the Python file using the following command:
```
pyuic5 design.ui -o ui.py
```
Notice that all of the program's logic is in `recorder.py` and the GUI is in `ui.py`. So, you can edit the GUI without touching the logic.