import argparse
import contextlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import six
import time

import numpy as np

import cupy


@contextlib.contextmanager
def timer(message):
    cupy.cuda.Stream.null.synchronize()
    start = time.time()
    yield
    cupy.cuda.Stream.null.synchronize()
    end = time.time()
    print('%s:  %f sec' % (message, end - start))


def use_custom_kernel(X, n_clusters, max_iter, elem):
    assert X.ndim == 2
    xp = cupy.get_array_module(X)
    pred = xp.zeros(len(X), dtype=np.int32)
    initial_indexes = np.random.choice(len(X), n_clusters,
                                       replace=False).astype(np.int32)
    centers = X[initial_indexes]
    data_num = X.shape[0]
    data_dim = X.shape[1]

    for _ in six.moves.range(max_iter):
        # calculate distances and label
        if not elem or xp == np:
            distances = xp.linalg.norm(X[:, None, :] - centers[None, :, :],
                                       axis=2)
        else:
            distances = xp.zeros((data_num, n_clusters), dtype=np.float32)
            cupy.ElementwiseKernel(
                'S data, raw S centers, int32 dim', 'raw S dist',
                '''
                int cent_ind1[] = {0, i % dim};
                int cent_ind2[] = {1, i % dim};
                int dist_ind1[] = {i / dim, 0};
                int dist_ind2[] = {i / dim, 1};
                double diff1 = centers[cent_ind1] - data;
                double diff2 = centers[cent_ind2] - data;
                atomicAdd(&dist[dist_ind1], diff1 * diff1);
                atomicAdd(&dist[dist_ind2], diff2 * diff2);
                ''',
                'calc_distances'
            )(X, centers, data_dim, distances)

        new_pred = xp.argmin(distances, axis=1).astype(np.int32)
        if xp.all(new_pred == pred):
            break
        pred = new_pred

        # calculate centers
        if not elem or xp == np:
            centers = xp.stack([X[pred == i].mean(axis=0)
                                for i in six.moves.range(n_clusters)])
        else:
            centers = xp.zeros((n_clusters, data_dim),
                               dtype=np.float32)
            group = xp.zeros(n_clusters, dtype=np.float32)
            label = pred[:, None]
            cupy.ElementwiseKernel(
                'S data, T label, int32 dim', 'raw S centers, raw S group',
                '''
                int cent_ind[] = {label, i % dim};
                atomicAdd(&centers[cent_ind], data);
                atomicAdd(&group[label], 1);
                ''',
                'calc_center'
            )(X, label, data_dim, centers, group)
            group /= data_dim
            centers /= group[:, None]

    return centers, pred


def draw(X, n_clusters, centers, pred, output):
    xp = cupy.get_array_module(X)
    for i in six.moves.range(n_clusters):
        labels = X[pred == i]
        if xp == cupy:
            labels = labels.get()
        plt.scatter(labels[:, 0], labels[:, 1], color=np.random.rand(3, 1))
    if xp == cupy:
        centers = centers.get()
    plt.scatter(centers[:, 0], centers[:, 1], s=120, marker='s',
                facecolors='y', edgecolors='k')
    plt.savefig(output + '.png')


def run(gpuid, n_clusters, max_iter, elem, output):
    samples = np.random.randn(5000000, 2).astype(np.float32)
    X_train = np.r_[samples + 1, samples - 1]
    repeat = 1

    with timer(' CPU '):
        for i in range(repeat):
            centers, pred = use_custom_kernel(X_train, n_clusters,
                                              max_iter, elem)

    with cupy.cuda.Device(gpuid):
        X_train = cupy.asarray(X_train)
        with timer(' GPU '):
            for i in range(repeat):
                centers, pred = use_custom_kernel(X_train, n_clusters,
                                                  max_iter, elem)
        if output is not None:
            index = np.random.choice(10000000, 300, replace=False)
            draw(X_train[index], n_clusters, centers, pred[index], output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu-id', '-g', default=0, type=int, dest='gpuid',
                        help='ID of GPU.')
    parser.add_argument('--n-clusters', '-n', default=2, type=int,
                        dest='n_clusters', help='number of clusters')
    parser.add_argument('--maxiter', '-m', default=10, type=int,
                        dest='max_iter', help='number of iterations')
    parser.add_argument('--elem', action='store_true', default=False,
                        help='use Elementwise kernel')
    parser.add_argument('--output-image', '-o', default=None, type=str,
                        dest='output', help='output image file name')
    args = parser.parse_args()
    if args.n_clusters != 2 and args.elem:
        msg = 'Can use Elementwise Kernel only when n-clusters is 2'
        raise ValueError(msg)
    run(args.gpuid, args.n_clusters, args.max_iter, args.elem, args.output)
