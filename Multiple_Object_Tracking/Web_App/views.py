#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Aug 27 10:26:59 2017

@author: dghy
"""

from django.shortcuts import render
import numpy as np
import cv2
import sys
import math
import matplotlib.pyplot as plt
from numpy import ma  # masked arrays

from scipy.spatial.distance import pdist
from scipy.spatial.distance import squareform
from scipy.linalg import inv
from numpy import dot

from filterpy.kalman import KalmanFilter
from filterpy.common import Q_discrete_white_noise

from munkres import Munkres, DISALLOWED
from scipy.optimize import linear_sum_assignment


def otsu_binary(img):
    """
    Otsu binarization function.
    :param img: Image to binarize - should be in greyscale.
    :return: Image after binarization.
    """
    # check if input image is in grayscale (2D)
    try:
        if img.shape[2]:
            # if there is 3rd dimension
            sys.exit('otsu_binary(img) input image should be in grayscale!')
    except IndexError:
        pass  # image doesn't have 3rd dimension - proceed

    # plt.close('all')
    blur = cv2.GaussianBlur(img, (5, 5), 0)
    # find normalized_histogram, and its cumulative distribution function
    hist = cv2.calcHist([blur], [0], None, [256], [0, 256])
    hist_norm = hist.ravel() / hist.max()
    Q = hist_norm.cumsum()
    bins = np.arange(256)
    fn_min = np.inf
    thresh = -1

    for i in range(1, 255):
        p1, p2 = np.hsplit(hist_norm, [i])  # probabilities
        q1 = Q[i]
        q2 = Q[255] - q1  # cum sum of classes
        b1, b2 = np.hsplit(bins, [i])  # weights
        # finding means and variances
        m1 = np.sum(p1 * b1) / q1
        m2 = np.sum(p2 * b2) / q2
        v1, v2 = np.sum(((b1 - m1) ** 2) * p1) / q1, np.sum(
            ((b2 - m2) ** 2) * p2) / q2
        # calculates the minimization function
        fn = v1 * q1 + v2 * q2
        if fn < fn_min:
            fn_min = fn
            thresh = i
    # find otsu's threshold value with OpenCV function
    ret, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY +
                              cv2.THRESH_OTSU)
    # print("{} {}".format(thresh, ret))

    ret, img_thresh1 = cv2.threshold(img, thresh, 255, cv2.THRESH_BINARY)
    return img_thresh1


def select_frames(video, frame_start, frame_stop):
    """
    Function that return selected frames from video.
    :param video: string, video whom frames are selected,
    :param frame_start: integer, frame from selection should be started
    :param frame_stop: integer, ending frame of selected section
    :return: video fragment <start_frame, stop_frame>
    """
    cap = cv2.VideoCapture(video)
    # font = cv2.FONT_HERSHEY_SIMPLEX
    video_fragment = []
    cap.set(1, frame_start)

    while cap.isOpened():
        ret, frame = cap.read()
        video_fragment.append(frame)
        if cv2.waitKey(1) & 0xFF == ord('q') or not ret \
                or (cap.get(1)) == frame_stop + 1:
            break
    # # img, text, (x,y), font, size, color, thickens
    #     cv2.putText(frame, str(round(cap.get(0)/1000, 2)) + 's',
    #                 (10, 15), font, 0.5, (255, 255, 255), 1)
    #     cv2.putText(frame, 'f.nr:' + str(cap.get(1)),
    #                 (100, 15), font, 0.5, (255, 255, 255), 1)
    #     cv2.imshow('frame', frame)

    cap.release()
    cv2.destroyAllWindows()
    return video_fragment


def read_image(path, name, ext, amount):
    """
    Function for reading images from folder. Name of images should be:
    name_index.extension so function can work automatic.
    Indexes should be in order! If they are not, function stops if image
    with next index is not found.
    Example: image_5.jpg -> read_image('path', 'image_', 'jpg', 50)
    :param path: string, path of images to read
    :param name: string, name of image without index
    :param ext: string, extension of image to read with ".", ex: '.jpg'
    :param amount: integer,
    :return: selected images as table if image exist or omits the image
    if it doesn't exist
    """
    images = []
    for i in range(amount):
        # try:
        print(path + '/' + name + str(i) + ext)
        img = cv2.imread(path + '/' + name + str(i) + ext, 1)
        # check if image was read
        try:
            if img.shape[0]:
                images.append(img)
        except AttributeError:
            pass
    return images


def blob_detect(img_with_blobs):
    params = cv2.SimpleBlobDetector_Params()
    # # Change thresholds
    # params.minThreshold = 10
    # params.maxThreshold = 200

    # Filter by Area.
    params.filterByArea = True
    params.minArea = 5

    # Filter by Circularity
    params.filterByCircularity = True
    params.minCircularity = 0.0

    # Filter by Convexity
    params.filterByConvexity = True
    params.minConvexity = 0.0

    # Filter by Inertia
    params.filterByInertia = True
    params.minInertiaRatio = 0.0

    # Create a detector with the parameters
    detector = cv2.SimpleBlobDetector_create(params)

    # get positions of blobs
    keypoints = detector.detect(img_with_blobs)

    # Draw detected blobs as red circles.
    # cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS ensures the size of the
    # circle corresponds to the size of blob
    im_with_keypoints = cv2.drawKeypoints(img_with_blobs, keypoints,
                                          np.array([]), (0, 0, 255),
                                          cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    return im_with_keypoints


def get_log_kernel(siz, std):
    """
    LoG(x,y) =
(1/(pi*sigma^4)) * (1 - (x^2+y^2)/(sigma^2)) * (e ^ (- (x^2 + y^2) / 2sigma^2)

    :param siz:
    :param std:
    :return:
    """
    x = np.linspace(-siz, siz, 2 * siz + 1)
    y = np.linspace(-siz, siz, 2 * siz + 1)
    x, y = np.meshgrid(x, y)
    arg = -(x ** 2 + y ** 2) / (2 * std ** 2)
    h = np.exp(arg)
    h[h < sys.float_info.epsilon * h.max()] = 0
    h = h / h.sum() if h.sum() != 0 else h
    h1 = h * (x ** 2 + y ** 2 - 2 * std ** 2) / (std ** 4)
    return h1 - h1.mean()


def img_inv(img):
    """
    Return inversion of an image.
    :param img: Input image.
    :return: Inverted image.
    """
    return cv2.bitwise_not(img)


def local_maxima(gray_image):
    """
    Finds local maxima in grayscale image.
    source:
    https://dsp.stackexchange.com/questions/17932/finding-local-
    brightness-maximas-with-opencv
    :param gray_image: Input 2D image.
    :return: Coordinates of local maxima points.
    """

    square_diameter_log_3 = 3  # 27x27

    total = gray_image
    for axis in range(2):
        d = 1
        for k in range(square_diameter_log_3):
            total = np.maximum(total, np.roll(total, d, axis))
            total = np.maximum(total, np.roll(total, -d, axis))
            d *= 3
    # if total == gray_iamge, maxima = total
    maxima = total == gray_image
    h, w = gray_image.shape
    result = []
    for j in range(h):
        for k in range(w):
            # gray_image[j][k] has float values!
            if maxima[j][k] and gray_image[j][k] * 255 > 1:
                # watch pixel coordinates output! (w, h)
                result.append((k, j))
    return result


def munkres(matrix):
    """
    Implementation of Hungarian algorithm for solving the Assignment Problem
    between measurements and estimates in multivariate linear kalman filter
    Example of usage:
        indexes = munkres(matrix)
    :param matrix: input matrix - should be a square cost matrix
    :return: index_list of tuples with assigned indexes,
             cost_list of assignment between indexes
    """

    # print_matrix(cost_matrix, msg='Cost matrix:')
    m = Munkres()

    indexes = m.compute(matrix)
    # print_matrix(matrix, msg='Highest profit through this matrix:')
    total = 0
    index_list = []
    cost_list = []
    for row, column in indexes:
        value = matrix[row][column]
        cost_list.append(value)
        total += value
        index_list.append((row, column))
        # print('({}, {}) -> {}'.format(row, column, value))
    # print('total profit={}'.format(total))
    return index_list, cost_list


def pair(prior, measurements):
    """
    Creates pairs between priors and measurement so each lays as close as
    possible to each other.
    Example of use:
    index = pair((60, 0), [(60, 0), (219, 37), (357, 55), (78, 82),
                 (301, 103), (202, 109), (376, 110)]))
    :param prior: prior state prediction (position) from Kalman filter, tuple
    :param measurements: positions from blob detection - measurements (x, y),
                 list of tuples
    :return: optimal pairs between estimate - measurement and cost of
             assigement between them
    """
    array = []
    array.append([prior[0][0], prior[0][1]])
    for measurement in measurements:
        array.append([measurement[0], measurement[1]])
    # count euclidean metric between priors and measurements
    metric = pdist(array, metric='euclidean')
    square = squareform(metric)
    min_index = []
    min_cost = []
    for index in munkres(square):
        # do not match to itself (distance = 0) and match only when distance
        # is low enough
        if square[index] != 0.0 and square[index] < 80:
            min_index.append(index)
            min_cost.append(square[index])
            # distance between indexes
            # print(square[index])
    return min_index, min_cost


# list of all VideoCapture methods and attributes
# [print(method) for method in dir(cap) if callable(getattr(cap, method))]

dt = 1.
R_var = 1
Q_var = 0.1
# state covariance matrix - no initial covariances, variances only
# [10^2 px, 10^2 px, ..] -
P = np.diag([100, 100, 10, 10, 1, 1])
# state transition matrix for 6 state variables (position - .. - acceleration,
# x, y)
F = np.array([[1, 0, dt, 0, 0.5 * pow(dt, 2), 0],
              [0, 1, 0, dt, 0, 0.5 * pow(dt, 2)],
              [0, 0, 1, 0, dt, 0],
              [0, 0, 0, 1, 0, dt],
              [0, 0, 0, 0, 1, 0],
              [0, 0, 0, 0, 0, 1]])
# x and y coordinates only:
H = np.array([[1., 0., 0., 0., 0., 0.],
              [0., 1., 0., 0., 0., 0.]])
# no initial corelation between x and y positions - variances only
R = np.array([[R_var, 0.], [0., R_var]])  # measurement covariance matrix
# Q must be the same shape as P
Q = np.diag([100, 100, 10, 10, 1, 1])  # model covariance matrix

start_frame = 400
stop_frame = 500
font = cv2.FONT_HERSHEY_SIMPLEX
vid_fragment = select_frames('CIMG4027.MOV', start_frame,
                             stop_frame)

height = vid_fragment[0].shape[0]
width = vid_fragment[0].shape[1]
# kernel for morphological operations
# check cv2.getStructuringElement() doc for more info
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
erosion_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

i = 0
bin_frames = []
# preprocess image loop
for frame in vid_fragment:
    if cv2.waitKey(15) & 0xFF == ord('q'):
        break
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    for m in range(height):  # height
        for n in range(width):  # width
            if n > 385 or m > 160:
                gray_frame[m][n] = 120

    # create a CLAHE object (Arguments are optional)
    # clahe = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(8, 8))
    # cl1 = clahe.apply(gray_frame)
    ret, th1 = cv2.threshold(gray_frame, 60, 255, cv2.THRESH_BINARY)
    # frame_thresh1 = otsu_binary(cl1)
    bin_frames.append(th1)
    if i % 10 == 0:
        print(i)
    i += 1

i = 0
maxima_points = []
# gather measurements loop
for frame in bin_frames:
    # prepare image - morphological operations
    erosion = cv2.erode(frame, erosion_kernel, iterations=1)
    opening = cv2.morphologyEx(erosion, cv2.MORPH_OPEN, kernel)
    dilate = cv2.dilate(opening, dilate_kernel, iterations=2)

    # create LoG kernel for finding local maximas
    log_kernel = get_log_kernel(30, 15)
    log_img = cv2.filter2D(dilate, cv2.CV_32F, log_kernel)
    # get local maximas of filtered image per frame
    maxima_points.append(local_maxima(log_img))
    if i % 10 == 0:
        print(i)
    i += 1

# create state vectors, max number of states - as much as frames
x = np.zeros((stop_frame, 6))
# state initialization - initial state is equal to measurements
m = 0
for i in range(len(maxima_points[0])):
    if maxima_points[0][i][0] > 0 and maxima_points[0][i][1] > 0:
        x[m] = [maxima_points[0][i][0], maxima_points[0][i][1], 0, 0, 0, 0]
        m += 1

est_number = 0
# number of estimates at the start
for point in maxima_points[::][0]:
    if point[0] > 0 and point[1] > 0:
        est_number += 1

# history of new objects appearance
new_obj_hist = [[]]
# difference between position of n-th object in m-1 frame and position of
# the same object in m frame
diff_2 = [[]]
# for how many frames given object was detected
frames_detected = []
# x and y posterior positions (estimates) for drawnings
x_est = [[] for i in range(stop_frame)]
y_est = [[] for i in range(stop_frame)]

# variable for counting frames where object has no measurement
striked_tracks = np.zeros(stop_frame)

new_detection = []

ff_nr = 0  # frame number
# kalman filter loop
for frame in range(stop_frame):
    # measurements in one frame
    frame_measurements = maxima_points[::][frame]
    measurements = []
    # make list of lists, not tuples; don't take zeros (assuming it's image)
    for meas in frame_measurements:
        if meas[0] > 0 and meas[1] > 0:
            measurements.append([meas[0], meas[1]])
    # count prior
    for i in range(est_number):
        x[i][::] = dot(F, x[i][::])
    P = dot(F, P).dot(F.T) + Q
    S = dot(H, P).dot(H.T) + R
    K = dot(P, H.T).dot(inv(S))

    ##########################################################################
    # prepare for update phase -> get (prior - measurement) assignment
    posterior_list = []
    for i in range(est_number):
        if not np.isnan(x[i][0]) and not np.isnan(x[i][1]):
            posterior_list.append(i)

    print('state\n', x[0:est_number, 0:2])
    print('\n')
    #    temp_matrix = np.array(x[0:est_number, 0:2])
    temp_matrix = np.array(x[posterior_list, 0:2])
    temp_matrix = np.append(temp_matrix, measurements, axis=0)
    print(temp_matrix)
    distance = pdist(temp_matrix, 'euclidean')  # returns vector

    # make square matrix out of vector
    distance = squareform(distance)
    temp_distance = distance
    # remove elements that are repeated - (0-1), (1-0) etc.
    #    distance = distance[est_number::, 0:est_number]
    distance = distance[len(posterior_list)::, 0:len(posterior_list)]

    # munkres
    row_index, column_index = linear_sum_assignment(distance)
    final_cost = distance[row_index, column_index].sum()
    index = []
    for i in range(len(row_index)):
        # index(object, measurement)
        index.append([row_index[i], column_index[i]])

    ##########################################################################
    # check if assignment is likely to be correct
    reject = np.ones(len(posterior_list))
    for i in range(len(posterior_list)):
        try:
            print('distance', index[i], distance[index[i][0], index[i][1]])
            #        print(distance[index[i][0], index[i][1]])
            if distance[index[i][0], index[i][1]] >= 10.:
                # distance to great - incorrect assignment
                #            index[i][1] = -1
                reject[i] = 0
        except IndexError:
            reject[i] = 0
            #    index *= reject

    ##########################################################################

    print('index before:\n', index)
    #    for i in range(len(posterior_list)):
    #        if i != posterior_list[i]:
    #            index[i][0] = posterior_list[i]
    #            print('correction')
    #
    #    print('index after:\n', index)
    ##########################################################################
    # update phase
    for i in range(len(index)):
        # find object that should get measurement next
        # count residual y: measurement - state
        if index[i][1] >= 0:
            #            try:
            y = np.array([measurements[index[i][1]] - dot(H, x[i, ::])])
            # posterior
            x[i, ::] = x[i, ::] + dot(K, y.T).T
            # append new positions
        if x[i][0] and x[i][1]:
            x_est[frame].append(x[i, 0])
            y_est[frame].append(x[i, 1])
    # posterior state covariance matrix
    P = dot(np.identity(6) - dot(K, H), P)
    #########################################################################
    # find new objects and create new states for them
    new_index = []
    measurment_indexes = []
    for i in range(len(index)):
        if index[i][1] >= 0.:
            measurment_indexes.append(index[i][1])

    for i in range(len(measurements)):
        if i not in measurment_indexes:
            new_index.append(i)
    new_detection.append([measurements[new_index[i]]
                          for i in range(len(new_index))])

    for i in range(len(new_detection[len(new_detection) - 1])):
        if new_detection[frame][i]:
            x[est_number + 1, ::] = [new_detection[frame][i][0],
                                     new_detection[frame][i][1], 0, 0, 0, 0]
            est_number += 1
            print('state added', est_number)
    ##########################################################################
    # find states without measurements and remove them
    no_track_list = []
    for i in range(len(reject)):
        if not reject[i]:
            no_track_list.append(i)
            #    print('no_trk_list', no_track_list)
    for track in no_track_list:
        if track >= 0:
            striked_tracks[track] += 1
            print('track/strikes', track, striked_tracks[track])
    for i in range(len(striked_tracks)):
        if striked_tracks[i] >= 1:
            x[i, ::] = [None, None, None, None, None, None]

            print('state_removed', i)

    ##########################################################################
    # draw measurements point loop

    if cv2.waitKey(30) & 0xFF == ord('q'):
        break
    # img, text, (x,y), font, size, color, thickens
    cv2.putText(vid_fragment[frame], 'f.nr:' + str(ff_nr),
                (100, 15), font, 0.5, (254, 254, 254), 1)

    # mark local maximas for every frame
    measurement_number = 0
    for point in measurements:
        cv2.circle(vid_fragment[frame], (point[0], point[1]), 5,
                   (0, 0, 255), 1)
        cv2.putText(vid_fragment[frame], str(measurement_number),
                    (point[0], point[1]), font, 0.5, (0, 0, 254), 1)
        measurement_number += 1

    for j in range(len(x)):
        if x[j][0] > 0 and x[j][1] > 0:
            # positions.append((x_est[i][j], y_est[i][j]))
            cv2.circle(vid_fragment[frame], (int(x[j][0]),
                                             int(x[j][1])), 3, (0, 255, 0), 1)
            cv2.putText(vid_fragment[frame], str(j),
                        (int(x[j][0] + 10), int(x[j][1] + 20)),
                        font, 0.5, (0, 254, 0), 1)
            #   TO DO:
            #       find a way to menage data consistency with Nan values!

    cv2.imshow('bin', vid_fragment[frame])
    cv2.waitKey(10)

    print(ff_nr, '--------------------------------------')
    ff_nr += 1
    input()

cv2.destroyAllWindows()

print('\nFinal estimates number:', est_number)

print('EOF - DONE')
