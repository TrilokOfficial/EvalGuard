import urllib.request
import os

os.makedirs('monitoring/models', exist_ok=True)
proto_ssd = 'https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt'
model_url = 'https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/MobileNetSSD_deploy.caffemodel'
proto_url = 'https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/MobileNetSSD_deploy.prototxt'

try:
    print("Downloading MobileNet SSD Prototxt...")
    urllib.request.urlretrieve(proto_url, 'monitoring/models/MobileNetSSD_deploy.prototxt')
    print("Downloading MobileNet SSD Caffe Model...")
    urllib.request.urlretrieve(model_url, 'monitoring/models/MobileNetSSD_deploy.caffemodel')
    print("Download complete.")
except Exception as e:
    print(f"Error downloading models: {e}")
