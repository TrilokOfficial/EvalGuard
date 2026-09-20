import cv2
import numpy as np
rmat = np.eye(3)
res = cv2.RQDecomp3x3(rmat)
print(type(res[0]), res[0])
