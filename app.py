from flask import Flask, render_template , request , jsonify, Response
from PIL import Image
import os , io , sys
import numpy as np 
import cv2
import base64
import imutils
import argparse
from scipy.spatial import distance as dist
from yolo_detection_images import runModel

app = Flask(__name__)
sub = cv2.createBackgroundSubtractorMOG2()  # create background substractor
MIN_CONF = 0.3
NMS_THRESH = 0.3
MIN_DISTANCE = 50

@app.route('/detectObject' , methods=['POST'])
def mask_image():
	# print(request.files , file=sys.stderr)
	file = request.files['image'].read() ## byte file
	npimg = np.fromstring(file, np.uint8)
	img = cv2.imdecode(npimg,cv2.IMREAD_COLOR)

	img = runModel(img)

	img = Image.fromarray(img.astype("uint8"))
	rawBytes = io.BytesIO()
	img.save(rawBytes, "JPEG")
	rawBytes.seek(0)
	img_base64 = base64.b64encode(rawBytes.read())
	return jsonify({'status':str(img_base64)})

@app.route('/test' , methods=['GET','POST'])
def test():
	print("log: got at test" , file=sys.stderr)
	return jsonify({'status':'succces'})

@app.route('/')
def home():
	return render_template('./index.html')

def gen():
    """Video streaming generator function."""
    cap = cv2.VideoCapture('pedestrians.mp4')
	#cap = cv2.VideoCapture('pedestrians2.avi')
	#cap = cv2.VideoCapture('pedestrians.mp4')

    # Read until video is completed
    while(cap.isOpened()):
        ret, frame = cap.read()  # import image
        if not ret: #if vid finish repeat
            frame = cv2.VideoCapture("pedestrians.mp4")
            continue
        if ret:  # if there is a frame continue with code
            image = cv2.resize(frame, (0, 0), None, 1, 1)  # resize image
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)  # converts image to gray
            fgmask = sub.apply(gray)  # uses the background subtraction
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))  # kernel to apply to the morphology
            closing = cv2.morphologyEx(fgmask, cv2.MORPH_CLOSE, kernel)
            opening = cv2.morphologyEx(closing, cv2.MORPH_OPEN, kernel)
            dilation = cv2.dilate(opening, kernel)
            retvalbin, bins = cv2.threshold(dilation, 220, 255, cv2.THRESH_BINARY)  # removes the shadows
            contours, hierarchy = cv2.findContours(dilation, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            minarea = 400
            maxarea = 50000
            for i in range(len(contours)):  # cycles through all contours in current frame
                if hierarchy[0, i, 3] == -1:  # using hierarchy to only count parent contours (contours not within others)
                    area = cv2.contourArea(contours[i])  # area of contour
                    if minarea < area < maxarea:  # area threshold for contour
                        # calculating centroids of contours
                        cnt = contours[i]
                        M = cv2.moments(cnt)
                        cx = int(M['m10'] / M['m00'])
                        cy = int(M['m01'] / M['m00'])
                        # gets bounding points of contour to create rectangle
                        # x,y is top left corner and w,h is width and height
                        x, y, w, h = cv2.boundingRect(cnt)
                        # creates a rectangle around contour
                        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        # Prints centroid text in order to double check later on
                        cv2.putText(image, str(cx) + "," + str(cy), (cx + 10, cy + 10), cv2.FONT_HERSHEY_SIMPLEX,.3, (0, 0, 255), 1)
                        cv2.drawMarker(image, (cx, cy), (0, 255, 255), cv2.MARKER_CROSS, markerSize=8, thickness=3,line_type=cv2.LINE_8)
        #cv2.imshow("countours", image)
        frame = cv2.imencode('.jpg', image)[1].tobytes()
        yield (b'--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        #time.sleep(0.1)
        key = cv2.waitKey(20)
        if key == 27:
           break     

def gen2():
	# construct the argument parse and parse the arguments
	'''ap = argparse.ArgumentParser()
	ap.add_argument("-i", "--input", type=str, default="",
		help="path to (optional) input video file")
	ap.add_argument("-o", "--output", type=str, default="",
		help="path to (optional) output video file")
	ap.add_argument("-d", "--display", type=int, default=1,
		help="whether or not output frame should be displayed")
	args = vars(ap.parse_args(["--input","pedestrians.mp4","--output","my_output.avi","--display","1"]))'''

	# load the COCO class labels our YOLO model was trained on
	labelsPath = "coco.names"
	LABELS = open(labelsPath).read().strip().split("\n")

	# derive the paths to the YOLO weights and model configuration
	weightsPath = "./yolov3.weights"
	configPath = "./cfg/yolov3.cfg"

	# load our YOLO object detector trained on COCO dataset (80 classes)
	print("[INFO] cargando YOLO desde el disco...")
	net = cv2.dnn.readNetFromDarknet(configPath, weightsPath)

	# determine only the *output* layer names that we need from YOLO
	ln = net.getLayerNames()
	ln = [ln[i[0] - 1] for i in net.getUnconnectedOutLayers()]

	# initialize the video stream and pointer to output video file
	print("[INFO] accediendo al input de video...")
	vs = cv2.VideoCapture("pedestrians.mp4")
	#vs = cv2.VideoCapture("pedestrians2.avi")
	#
	#vs = cv2.VideoCapture(0)

	#writer = None

	# loop over the frames from the video stream
	while True:
		# read the next frame from the file
		(grabbed, frame) = vs.read()

		# if the frame was not grabbed, then we have reached the end
		# of the stream
		if not grabbed:
			break

		# resize the frame and then detect people (and only people) in it
		frame = imutils.resize(frame, width=700)
		results = detect_people(frame, net, ln, personIdx=LABELS.index("person"))

		# initialize the set of indexes that violate the minimum social
		# distance
		violate = set()

		# ensure there are *at least* two people detections (required in
		# order to compute our pairwise distance maps)
		if len(results) >= 2:
			# extract all centroids from the results and compute the
			# Euclidean distances between all pairs of the centroids
			centroids = np.array([r[2] for r in results])
			D = dist.cdist(centroids, centroids, metric="euclidean")

			# loop over the upper triangular of the distance matrix
			for i in range(0, D.shape[0]):
				for j in range(i + 1, D.shape[1]):
					# check to see if the distance between any two
					# centroid pairs is less than the configured number
					# of pixels
					if D[i, j] < MIN_DISTANCE:
						# update our violation set with the indexes of
						# the centroid pairs
						violate.add(i)
						violate.add(j)

		# loop over the results
		for (i, (prob, bbox, centroid)) in enumerate(results):
			# extract the bounding box and centroid coordinates, then
			# initialize the color of the annotation
			(startX, startY, endX, endY) = bbox
			(cX, cY) = centroid
			color = (0, 255, 0)

			# if the index pair exists within the violation set, then
			# update the color
			if i in violate:
				color = (0, 0, 255)

			# draw (1) a bounding box around the person and (2) the
			# centroid coordinates of the person,
			cv2.rectangle(frame, (startX, startY), (endX, endY), color, 2)
			cv2.circle(frame, (cX, cY), 5, color, 1)

		# draw the total number of social distancing violations on the
		# output frame
		text = "Violaciones en Distanciamiento Social: {}".format(len(violate))
		cv2.putText(frame, text, (10, frame.shape[0] - 25),
			cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 0, 255), 3)

		# check to see if the output frame should be displayed to our
		# screen
		'''if args["display"] > 0:
			# show the output frame
			#cv2_imshow(frame)
			key = cv2.waitKey(1) & 0xFF

			# if the `q` key was pressed, break from the loop
			if key == ord("q"):
				break

		# if an output video file path has been supplied and the video
		# writer has not been initialized, do so now
		if args["output"] != "" and writer is None:
			# initialize our video writer
			fourcc = cv2.VideoWriter_fourcc(*"MJPG")
			writer = cv2.VideoWriter(args["output"], fourcc, 25,
				(frame.shape[1], frame.shape[0]), True)'''

		# if the video writer is not None, write the frame to the output
		# video file
		'''if writer is not None:
			writer.write(frame)	  '''
		
		frame = cv2.imencode('.jpg', frame).tobytes()
		yield (b'--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
		#time.sleep(0.1)

@app.route('/video_feed')
def video_feed():
    """Video streaming route. Put this in the src attribute of an img tag."""
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
	#return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

	
@app.after_request
def after_request(response):
    print("log: estableciendo cores" , file = sys.stderr)
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response

def detect_people(frame, net, ln, personIdx=0):
	# grab the dimensions of the frame and  initialize the list of
	# results
	(H, W) = frame.shape[:2]
	results = []

	# construct a blob from the input frame and then perform a forward
	# pass of the YOLO object detector, giving us our bounding boxes
	# and associated probabilities
	blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (416, 416),
		swapRB=True, crop=False)
	net.setInput(blob)
	layerOutputs = net.forward(ln)

	# initialize our lists of detected bounding boxes, centroids, and
	# confidences, respectively
	boxes = []
	centroids = []
	confidences = []

	# loop over each of the layer outputs
	for output in layerOutputs:
		# loop over each of the detections
		for detection in output:
			# extract the class ID and confidence (i.e., probability)
			# of the current object detection
			scores = detection[5:]
			classID = np.argmax(scores)
			confidence = scores[classID]

			# filter detections by (1) ensuring that the object
			# detected was a person and (2) that the minimum
			# confidence is met
			if classID == personIdx and confidence > MIN_CONF:
				# scale the bounding box coordinates back relative to
				# the size of the image, keeping in mind that YOLO
				# actually returns the center (x, y)-coordinates of
				# the bounding box followed by the boxes' width and
				# height
				box = detection[0:4] * np.array([W, H, W, H])
				(centerX, centerY, width, height) = box.astype("int")

				# use the center (x, y)-coordinates to derive the top
				# and and left corner of the bounding box
				x = int(centerX - (width / 2))
				y = int(centerY - (height / 2))

				# update our list of bounding box coordinates,
				# centroids, and confidences
				boxes.append([x, y, int(width), int(height)])
				centroids.append((centerX, centerY))
				confidences.append(float(confidence))

	# apply non-maxima suppression to suppress weak, overlapping
	# bounding boxes
	idxs = cv2.dnn.NMSBoxes(boxes, confidences, MIN_CONF, NMS_THRESH)

	# ensure at least one detection exists
	if len(idxs) > 0:
		# loop over the indexes we are keeping
		for i in idxs.flatten():
			# extract the bounding box coordinates
			(x, y) = (boxes[i][0], boxes[i][1])
			(w, h) = (boxes[i][2], boxes[i][3])

			# update our results list to consist of the person
			# prediction probability, bounding box coordinates,
			# and the centroid
			r = (confidences[i], (x, y, x + w, y + h), centroids[i])
			results.append(r)

	# return the list of results
	return results

if __name__ == '__main__':
	app.run(debug = True)
