from ultralytics import YOLO

m = YOLO(r"D:\Fishy\server\Yolo\11s2.pt")
print(type(m.model.names))
print(len(m.model.names))
print(m.model.names)