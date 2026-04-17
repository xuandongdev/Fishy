from ultralytics import YOLO

model = YOLO(r"D:\Fishy\server\Yolo\11s2.pt")
model.export(format="tflite", imgsz=320, nms=False, half=True)