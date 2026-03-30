from ultralytics import YOLO

m = YOLO(r"D:/Fishy/server/Yolo/Models/12mNew.pt")
print(type(m.model.names))
print(len(m.model.names))
print(m.model.names)