import taichi_lang as ti
import math
import numpy as np
import cv2
import matplotlib
import matplotlib.pyplot as plt
from imageio import imread, imwrite

real = ti.f32
ti.set_default_fp(real)

num_iterations = 32
n_grid = 110
dx = 1.0 / n_grid
num_iterations_gauss_seidel = 10
p_dims = num_iterations_gauss_seidel + 1
steps = 100
learning_rate = 0.01

scalar = lambda: ti.var(dt=real)

vx = scalar()
vy = scalar()
div = scalar()
p = scalar()
vx_updated = scalar()
vy_updated = scalar()
target = scalar()
smoke = scalar()
loss = scalar()

# ti.cfg.arch = ti.cuda

@ti.layout
def place():
  ti.root.dense(ti.l, num_iterations * p_dims).dense(ti.ij, n_grid).place(p)
  ti.root.dense(ti.l, steps).dense(ti.ij, n_grid).place(vx, vy, smoke, div)
  ti.root.dense(ti.ij, n_grid).place(target)
  ti.root.dense(ti.ij, n_grid).place(vx_updated, vy_updated)
  ti.root.place(loss)
  ti.root.lazy_grad()


# TODO: merge these into a single @ti.func
# Integer modulo operator for negative values of n
@ti.func
def nimod(n, divisor):
  return divisor + n - divisor * (-n // divisor)

# Integer modulo operator for positive values of n
@ti.func
def imod(n, divisor):
  return n - divisor * (n // divisor)

@ti.func
def dec_index(index):
  new_index = index - 1
  if new_index < 0:
    new_index = n_grid - 1
  return new_index

@ti.func
def inc_index(index):
  new_index = index + 1
  if new_index >= n_grid:
    new_index = 0
  return new_index


@ti.kernel
def compute_div(t: ti.i32):
  for y in range(n_grid):
    for x in range(n_grid):
      div[t, y, x] = -0.5 * dx * (vx_updated[inc_index(y), x]  - vx_updated[dec_index(y), x] + vy_updated[y, inc_index(x)] - vy_updated[y, dec_index(x)])

@ti.kernel
def compute_p(t:ti.i32, k: ti.i32):
  for y in range(n_grid):
    for x in range(n_grid):
      a = k + t * num_iterations_gauss_seidel
      p[a + 1, y, x] = (div[t, y, x] + p[a, dec_index(y), x] + p[a, inc_index(y), x] + p[a, y, dec_index(x)] + p[a, y, inc_index(x)]) / 4.0

@ti.kernel
def update_v(t: ti.i32):
  for y in range(n_grid):
    for x in range(n_grid):
      a = num_iterations_gauss_seidel * t - 1
      vx[t, y, x] = vx_updated[y, x] - 0.5 * (p[a, inc_index(y), x] - p[a, dec_index(y), x]) / dx
      vy[t, y, x] = vy_updated[y, x] - 0.5 * (p[a, y, inc_index(x)] - p[a, y, dec_index(x)]) / dx

@ti.kernel
def advect_smoke(t: ti.i32):
  """Move field smoke according to x and y velocities (vx and vy)
     using an implicit Euler integrator."""
  for y in range(n_grid):
    for x in range(n_grid):
      center_x = y - vx[t, y, x]
      center_y = x - vy[t, y, x]

      # Compute indices of source cell
      left_ix = ti.cast(ti.floor(center_x), ti.i32)
      top_ix = ti.cast(ti.floor(center_y), ti.i32)

      rw = center_x - left_ix # Relative weight of right-hand cell
      bw = center_y - top_ix # Relative weight of bottom cell

      # Wrap around edges
      # TODO: implement mod (%) operator
      if left_ix < 0:
        left_ix = nimod(left_ix, n_grid)
      else:
        left_ix = imod(left_ix, n_grid)

      right_ix = left_ix + 1
      if right_ix < 0:
        right_ix = nimod(right_ix, n_grid)
      else:
        right_ix = imod(right_ix, n_grid)

      if top_ix < 0:
        top_ix = nimod(top_ix, n_grid)
      else:
        top_ix = imod(top_ix, n_grid)

      bot_ix = top_ix + 1
      if bot_ix < 0:
        bot_ix = nimod(bot_ix, n_grid)
      else:
        bot_ix = imod(bot_ix, n_grid)

      # Linearly-weighted sum of the 4 surrounding cells
      smoke[t, y, x] = (1 - rw) * ((1 - bw)*smoke[t - 1, left_ix,  top_ix] + bw*smoke[t - 1, left_ix,  bot_ix]) + rw * ((1 - bw)*smoke[t - 1, right_ix, top_ix] + bw*smoke[t - 1, right_ix, bot_ix])

@ti.kernel
def advect_vy(t: ti.i32):
  """Move field vy according to x and y velocities (vx and vy)
     using an implicit Euler integrator."""
  for y in range(n_grid):
    for x in range(n_grid):
      center_x = y - vx[t - 1, y, x]
      center_y = x - vy[t - 1, y, x]

      # Compute indices of source cell
      left_ix = ti.cast(ti.floor(center_x), ti.i32)
      top_ix = ti.cast(ti.floor(center_y), ti.i32)

      rw = center_x - left_ix # Relative weight of right-hand cell
      bw = center_y - top_ix # Relative weight of bottom cell

      # Wrap around edges
      # TODO: implement mod (%) operator
      if left_ix < 0:
        left_ix = nimod(left_ix, n_grid)
      else:
        left_ix = imod(left_ix, n_grid)

      right_ix = left_ix + 1
      if right_ix < 0:
        right_ix = nimod(right_ix, n_grid)
      else:
        right_ix = imod(right_ix, n_grid)

      if top_ix < 0:
        top_ix = nimod(top_ix, n_grid)
      else:
        top_ix = imod(top_ix, n_grid)

      bot_ix = top_ix + 1
      if bot_ix < 0:
        bot_ix = nimod(bot_ix, n_grid)
      else:
        bot_ix = imod(bot_ix, n_grid)

      # Linearly-weighted sum of the 4 surrounding cells
      vy_updated[y, x] = (1 - rw) * ((1 - bw)*vy[t - 1, left_ix,  top_ix] + bw*vy[t - 1, left_ix,  bot_ix]) \
                 + rw * ((1 - bw)*vy[t - 1, right_ix, top_ix] + bw*vy[t - 1, right_ix, bot_ix])

@ti.kernel
def advect_vx(t: ti.i32):
  """Move field vx according to x and y velocities (vx and vy)
     using an implicit Euler integrator."""
  for y in range(n_grid):
    for x in range(n_grid):
      center_x = y - vx[t - 1, y, x]
      center_y = x - vy[t - 1, y, x]

      # Compute indices of source cell
      left_ix = ti.cast(ti.floor(center_x), ti.i32)
      top_ix = ti.cast(ti.floor(center_y), ti.i32)

      rw = center_x - left_ix # Relative weight of right-hand cell
      bw = center_y - top_ix # Relative weight of bottom cell

      # Wrap around edges
      # TODO: implement mod (%) operator
      if left_ix < 0:
        left_ix = nimod(left_ix, n_grid)
      else:
        left_ix = imod(left_ix, n_grid)

      right_ix = left_ix + 1
      if right_ix < 0:
        right_ix = nimod(right_ix, n_grid)
      else:
        right_ix = imod(right_ix, n_grid)

      if top_ix < 0:
        top_ix = nimod(top_ix, n_grid)
      else:
        top_ix = imod(top_ix, n_grid)

      bot_ix = top_ix + 1
      if bot_ix < 0:
        bot_ix = nimod(bot_ix, n_grid)
      else:
        bot_ix = imod(bot_ix, n_grid)

      # Linearly-weighted sum of the 4 surrounding cells
      vx_updated[y, x] = (1 - rw) * ((1 - bw)*vx[t - 1, left_ix,  top_ix] + bw*vx[t - 1, left_ix,  bot_ix]) \
                 + rw * ((1 - bw)*vx[t - 1, right_ix, top_ix] + bw*vx[t - 1, right_ix, bot_ix])


@ti.kernel
def compute_loss():
  for i in range(n_grid):
    for j in range(n_grid):
      ti.atomic_add(loss, ti.sqr(target[i, j] - smoke[steps - 1, i, j]) * (1 / n_grid ** 2))

@ti.kernel
def apply_grad():
  # gradient descent
  for i, j in vx.grad:
    vx[0, i, j] -= learning_rate * vx.grad[0, i, j]

  for i, j in vy.grad:
    vy[0, i, j] -= learning_rate * vy.grad[0, i, j]

def forward(output=None):
  for t in range(1, steps):
    advect_vx(t)
    advect_vy(t)

    compute_div(t)
    for k in range(num_iterations_gauss_seidel):
      compute_p(t, k)

    update_v(t)
    advect_smoke(t)

    if output:
      smoke_ = np.zeros(shape=(n_grid, n_grid), dtype=np.float32)
      for i in range(n_grid):
        for j in range(n_grid):
          smoke_[i, j] = smoke[t, i, j]
      cv2.imshow('smoke', smoke_)
      cv2.waitKey(1)
      matplotlib.image.imsave("{}/{:04d}.png".format(output, t), 255 * smoke_)
  compute_loss()

def main():
  print("Loading initial and target states...")
  initial_smoke_img = imread("init_smoke.png")[:, :, 0] / 255.0
  target_img = imread("peace.png")[::2, ::2, 3] / 255.0

  for i in range(n_grid):
    for j in range(n_grid):
      target[i, j] = float(target_img[i, j])
      vx[0, i, j] = (i - 0.5 * j) * 0.01
      # vx[0, i, j] = 0
      vy[0, i, j] = 0
      smoke[0, i, j] = float(initial_smoke_img[i, j])

  for opt in range(num_iterations):
    with ti.Tape(loss):
      forward("test")

    print('Iter', opt, ' Loss =', loss[None])

    apply_grad()

  forward("output")

if __name__ == '__main__':
  main()

