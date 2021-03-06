# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Special Math Ops."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import math
import numpy as np

from tensorflow.python.framework import constant_op
from tensorflow.python.framework import ops
from tensorflow.python.ops import math_ops

__all__ = [
    "ndtr",
    "log_ndtr",
]


# log_ndtr uses different functions over the ranges
# (-infty, lower](lower, upper](upper, infty)
# Lower bound values were chosen by examining where the support of ndtr
# appears to be zero, relative to scipy's (which is always 64bit). They were
# then made more conservative just to be safe. (Conservative means use the
# expansion more than we probably need to.) See `NdtrTest` in
# special_math_test.py.
LOGNDTR_FLOAT64_LOWER = -20
LOGNDTR_FLOAT32_LOWER = -10
# Upper bound values were chosen by examining for which values of 'x'
# Log[cdf(x)] is 0, after which point we need to use the approximation
# Log[cdf(x)] = Log[1 - cdf(-x)] approx -cdf(-x).  We chose a value slightly
# conservative, meaning we use the approximation earlier than needed.
LOGNDTR_FLOAT32_UPPER = 5
LOGNDTR_FLOAT64_UPPER = 8


def ndtr(x, name=None):
  """Normal distribution function.

  Returns the area under the Gaussian probability density function, integrated
  from minus infinity to x:

  ```
                    1       / x
     ndtr(x)  = ----------  |    exp(-0.5 t^2) dt
                sqrt(2 pi)  /-inf

              = 0.5 (1 + erf(x / sqrt(2)))
              = 0.5 erfc(x / sqrt(2))
  ```

  Args:
    x: `Tensor` of type `float32`, `float64`.
    name: Python string. A name for the operation (default="ndtr").

  Returns:
    ndtr: `Tensor` with `dtype=x.dtype`.

  Raises:
    TypeError: if `x` is not floating-type.
  """

  with ops.name_scope(name, "ndtr", values=[x]):
    x = ops.convert_to_tensor(x, name="x")
    if x.dtype.as_numpy_dtype not in [np.float32, np.float64]:
      raise TypeError(
          "x.dtype=%s is not handled, see docstring for supported types."
          % x.dtype)
    return _ndtr(x)


def _ndtr(x):
  """Implements ndtr core logic."""
  half_sqrt_2 = constant_op.constant(
      0.5 * math.sqrt(2.), dtype=x.dtype, name="half_sqrt_2")
  w = x * half_sqrt_2
  z = math_ops.abs(w)
  y = math_ops.select(math_ops.less(z, half_sqrt_2),
                      1. + math_ops.erf(w),
                      math_ops.select(math_ops.greater(w, 0.),
                                      2. - math_ops.erfc(z),
                                      math_ops.erfc(z)))
  return 0.5 * y


def log_ndtr(x, series_order=3, name=None):
  """Log Normal distribution function.

  For details of the Normal distribution function see `ndtr`.

  This function calculates `(log o ndtr)(x)` by either calling `log(ndtr(x))` or
  using an asymptotic series.  Specifically:
  - For `x > upper_segment`, use the approximation `-ndtr(-x)` based on
    `log(1-x) ~= -x, x << 1`.
  - For `lower_segment < x <= upper_segment`, use the existing `ndtr` technique
    and take a log.
  - For `x <= lower_segment`, we use the series approximation of erf to compute
    the log CDF directly.

  The `lower_segment` is set based on the precision of the input:

  ```
  lower_segment = { -20.  x.dtype=float64
                  { -10,  x.dtype=float32
  upper_segment = {   8.  x.dtype=float64
                  {   5,  x.dtype=float32
  ```

  When `x < lower_segment`, the `ndtr` asymptotic series approximation is:

  ```
     ndtr(x) = scale * (1 + sum) + R_N
     scale   = exp(-0.5 x^2) / (-x sqrt(2 pi))
     sum     = Sum{(-1)^n (2n-1)!! / (x^2)^n, n=1:N}
     R_N     = O(exp(-0.5 x^2) (2N+1)!! / |x|^{2N+3})
  ```

  where `(2n-1)!! = (2n-1) (2n-3) (2n-5) ... (3) (1)` is a
  [double-factorial](https://en.wikipedia.org/wiki/Double_factorial).


  Args:
    x: `Tensor` of type `float32`, `float64`.
    series_order: Positive Python `integer`. Maximum depth to
      evaluate the asymptotic expansion.  This is the `N` above.
    name: Python string. A name for the operation (default="log_ndtr").

  Returns:
    log_ndtr: `Tensor` with `dtype=x.dtype`.

  Raises:
    TypeError: if `x.dtype` is not handled.
    TypeError: if `series_order` is a not Python `integer.`
    ValueError:  if `series_order` is not in `[1, 30]`.
  """
  if not isinstance(series_order, int):
    raise TypeError("series_order must be a Python integer.")
  if series_order < 1:
    raise ValueError("series_order must be positive.")
  if series_order > 30:
    raise ValueError("series_order must be <= 30.")

  with ops.name_scope(name, "log_ndtr", values=[x]):
    x = ops.convert_to_tensor(x, name="x")

    if x.dtype.as_numpy_dtype == np.float64:
      lower_segment = LOGNDTR_FLOAT64_LOWER
      upper_segment = LOGNDTR_FLOAT64_UPPER
    elif x.dtype.as_numpy_dtype == np.float32:
      lower_segment = LOGNDTR_FLOAT32_LOWER
      upper_segment = LOGNDTR_FLOAT32_UPPER
    else:
      raise TypeError("x.dtype=%s is not supported." % x.dtype)

    # The basic idea here was ported from py/scipy/special/cephes/ndtr.c.
    # We copy the main idea, with a few changes
    # * For x >> 1, and X ~ Normal(0, 1),
    #     Log[P[X < x]] = Log[1 - P[X < -x]] approx -P[X < -x],
    #     which extends the range of validity of this function.
    # * We use one fixed series_order for all of 'x', rather than adaptive.
    # * Our docstring properly reflects that this is an asymptotic series, not a
    #   Tayor series.  We also provided a correct bound on the remainder.

    return math_ops.select(
        math_ops.greater(x, upper_segment),
        -_ndtr(-x),  # log(1-x) ~= -x, x << 1
        math_ops.select(math_ops.greater(x, lower_segment),
                        math_ops.log(_ndtr(x)),
                        _log_ndtr_lower(x, series_order)))


def _log_ndtr_lower(x, series_order):
  """Asymptotic expansion version of `Log[cdf(x)]`, apppropriate for `x<<-1`."""
  x_2 = math_ops.square(x)
  # Log of the term multiplying (1 + sum)
  log_scale = -0.5 * x_2 - math_ops.log(-x) - 0.5 * math.log(2. * math.pi)

  # Compute the summation.
  even_sum = 0.
  odd_sum = 0.
  x_2n = x_2  # Start with x^{2*1} = x^{2*n} with n = 1.
  for n in range(1, series_order + 1):
    if n % 2:
      odd_sum -= _double_factorial(2 * n - 1) / x_2n
    else:
      even_sum += _double_factorial(2 * n - 1) / x_2n
    x_2n *= x_2

  return log_scale + math_ops.log(1. + even_sum + odd_sum)


def _double_factorial(n):
  """The double factorial function for small Python integer `n`."""
  return np.prod(np.arange(n, 1, -2))
