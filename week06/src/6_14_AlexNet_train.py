import os
import numpy as np
from PIL import Image
import tensorflow as tf
from sklearn.model_selection import train_test_split
os.environ['CUDA_VISIBLE_DEVICES'] = '1'

"""
train the dataset from scratch
"""
# Image Parameters
N_CLASSES = 2  # CHANGE HERE, total number of classes
IMG_HEIGHT = 224  # CHANGE HERE, the image height to be resized to
IMG_WIDTH = 224  # CHANGE HERE, the image width to be resized to
CHANNELS = 3  # The 3 color channels, change to 1 if grayscale
dropout = 0.3
num_steps = 10000
train_display = 100
val_display = 1000
learning_rate = 0.0001
BATCHSIZE = 64
save_check = 1000
DATASET_PATH = '/raid/bruce/dog_cat/train/'  # the dataset file or root folder path.


def get_files_path(file_dir):
    cats = list()
    dogs = list()
    label_cats = list()
    label_dogs = list()
    for file in os.listdir(file_dir):
        name = file.split(sep='.')
        if name[0] == 'cat':
            cats.append(file_dir+file)
            label_cats.append(0)
        else:
            dogs.append(file_dir+file)
            label_dogs.append(1)

    print("there are %d cats and there are %d dogs" % (len(cats), len(dogs)))
    image_list = np.hstack((cats, dogs))
    label_list = np.hstack((label_cats, label_dogs))
    temp = np.array([image_list, label_list])
    temp = temp.transpose()
    np.random.shuffle(temp)
    image_list = list(temp[:, 0])
    label_list = list(temp[:, 1])
    label_list = [int(i) for i in label_list]
    return image_list, label_list


def _parse_function(imagepaths, labels):
    """
    数据预处理环节
    :param imagepaths:
    :param labels:
    :return:
    """
    image_string = tf.read_file(imagepaths)
    image_decode = tf.image.decode_jpeg(image_string, channels=CHANNELS)
    image_decode = tf.image.convert_image_dtype(image_decode, tf.float32)
    image_resized = tf.image.resize_images(image_decode, [IMG_HEIGHT, IMG_WIDTH], method=tf.image.ResizeMethod.AREA)
    return image_resized, labels


def training_preprocess(image, label):
    image = tf.image.random_flip_left_right(image)  # img random flipped from left to right
    image = tf.random_crop(image, [IMG_HEIGHT, IMG_WIDTH, 3])  # img random crop with crop size,
    image = image / 255.0
    image = image - 0.5
    image = image * 2.0
    return image, label


def val_preprocess(image, label):
    # Central crop!
    image = tf.image.resize_image_with_crop_or_pad(image, IMG_HEIGHT, IMG_WIDTH)
    image = image / 255.0
    image = image - 0.5
    image = image * 2.0
    return image, label


is_training = tf.placeholder(tf.bool)
image, labels = get_files_path(DATASET_PATH)
image_train, image_test, label_train, label_test = train_test_split(image, labels, test_size=0.25, random_state=0)

assert image.__len__() == labels.__len__()

traindata = tf.data.Dataset.from_tensor_slices((image_train, label_train)).\
    map(_parse_function).map(training_preprocess).repeat().batch(BATCHSIZE).prefetch(BATCHSIZE)

valdata = tf.data.Dataset.from_tensor_slices((image_test, label_test)).\
    map(_parse_function).map(val_preprocess).repeat().batch(BATCHSIZE).prefetch(BATCHSIZE)


iterator = tf.data.Iterator.from_structure(traindata.output_types, traindata.output_shapes)
X, Y = iterator.get_next()


traindata_init = iterator.make_initializer(traindata)
valdata_init = iterator.make_initializer(valdata)


def check_accuracy(sess, correct_prediction, is_training, dataset_init_op, batches_to_check):
    # Initialize the validation dataset
    sess.run(dataset_init_op)
    num_correct, num_samples = 0, 0
    for i in range(batches_to_check):
        try:
            correct_pred = sess.run(correct_prediction, {is_training: False})
            num_correct += correct_pred.sum()
            num_samples += correct_pred.shape[0]
        except tf.errors.OutOfRangeError:
            break
    acc = float(num_correct) / num_samples
    return acc


# Define the newwork
def conv_net(x, n_classes, dropout, reuse, is_training):
    # Define a scope for reusing the variables
    with tf.variable_scope('ConvNet', reuse=reuse):
        # Convolution Layer with 32 filters and a kernel size of 5
        x = tf.reshape(x, shape=[-1, 224, 224, 3])
        # Convolution Layer with 32 filters and a kernel size of 5
        conv1 = tf.layers.conv2d(x, 96, 11, 4, activation=tf.nn.relu)
        # Max Pooling (down-sampling) with strides of 2 and kernel size of 2
        pool1 = tf.layers.max_pooling2d(conv1, 3, 2)

        # Convolution Layer with 32 filters and a kernel size of 5
        conv2_1 = tf.layers.conv2d(pool1, 256, 5, padding='same', activation=tf.nn.relu)
        # Max Pooling (down-sampling) with strides of 2 and kernel size of 2
        pool2 = tf.layers.max_pooling2d(conv2_1, 3, 2)

        conv3_1 = tf.layers.conv2d(pool2, 384, 3, padding='same', activation=tf.nn.relu)
        conv3_2 = tf.layers.conv2d(conv3_1, 384, 3, padding='same', activation=tf.nn.relu)
        conv3_3 = tf.layers.conv2d(conv3_2, 384, 3, padding='same', activation=tf.nn.relu)

        pool3 = tf.layers.max_pooling2d(conv3_3, 3, 2)

        # Flatten the data to a 1-D vector for the fully connected layer
        fc1 = tf.contrib.layers.flatten(pool3)

        # Fully connected layer (in contrib folder for now)
        fc1 = tf.layers.dense(fc1, 4096)
        # Apply Dropout (if is_training is False, dropout is not applied)
        fc1 = tf.layers.dropout(fc1, rate=dropout, training=is_training)

        fc2 = tf.layers.dense(fc1, 4096)
        fc2 = tf.layers.dropout(fc2, rate=dropout, training=is_training)
        # Output layer, class prediction
        out = tf.layers.dense(fc2, n_classes)
        # Because 'softmax_cross_entropy_with_logits' already apply softmax,
        # we only apply softmax to testing network
        out = tf.nn.softmax(out) if not is_training else out
        # out = tf.nn.softmax(out)
    return out


# Create a graph for training
logits_train = conv_net(X, N_CLASSES, dropout, reuse=False, is_training=is_training)
# Create another graph for testing that reuse the same weights, 注意测试的时候不丢弃网络
logits_test = conv_net(X, N_CLASSES, dropout=0.0, reuse=True, is_training=is_training)

# Define loss and optimizer (with train logits, for dropout to take effect)
loss_op = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(logits=logits_train, labels=Y))
optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
train_op = optimizer.minimize(loss_op)

# Evaluate model (with test logits, for dropout to be disabled)
correct_pred = tf.equal(tf.argmax(logits_test, 1), tf.cast(Y, tf.int64))
accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

# Initialize the variables (i.e. assign their default value)
init = tf.global_variables_initializer()

# Start training
# Initialize the iterator
with tf.Session() as sess:
    # sess.run(iterator.initializer)
    sess.run(init)
    sess.run(traindata_init)
    saver = tf.train.Saver(max_to_keep=3)
    ckpt = tf.train.get_checkpoint_state('./model_alexnet')
    if ckpt is None:
        print("Model not found, please train your model first...")
    else:
        path = ckpt.model_checkpoint_path
        print('loading pre-trained model from %s.....' % path)
        saver.restore(sess, path)
    # Training cycle
    for step in range(1, num_steps + 1):
        sess.run(train_op)
        if step % train_display == 0 or step == 1:
            # Run optimization and calculate batch loss and accuracy
            loss, acc = sess.run([loss_op, accuracy, {is_training: True}])
            print("Step " + str(step) + ", Minibatch Loss= " + "{:.4f}".format(loss) + ", Training Accuracy= " +
                  "{:.3f}".format(acc))

        if step % val_display == 0 and step is not 0:
            # sess.run(valdata_init)
            avg_acc = 0
            loss = sess.run(loss_op, {is_training: False})
            acc = check_accuracy(sess, correct_pred, False, valdata_init, val_display)
            print("\033[1;36m=\033[0m"*60)
            print("\033[1;36mStep %d, Minibatch Loss= %.4f, Test Accuracy= %.4f\033[0m" % (step, loss, acc))
            print("\033[1;36m=\033[0m"*60)

        if step % 1000 == 0:
            path_name = "./model_alexnet/model" + str(step) + ".ckpt"
            print(path_name)
            saver.save(sess, path_name)
            print("model has been saved")

    print("Optimization Finished!")
