#!/usr/bin/env python3
#------------------------------------------------------------------------------
# Declare all the subclasses and method overrides central to this library
# TODO: Add feature to draw axes in *row-major* or *column-major* mode
#------------------------------------------------------------------------------#
# Decorators used a lot here; below is very simple example that demonstrates
# how simple decorator decorators work
# def decorator1(func):
#     def decorator():
#         print('decorator 1 called')
#         func()
#         print('decorator 1 finished')
#     return decorator
# def decorator2(func):
#     def decorator():
#         print('decorator 2 called')
#         func()
#         print('decorator 2 finished')
#     return decorator
# @decorator1
# @decorator2
# def hello():
#     print('hello world!')
# hello()
#------------------------------------------------------------------------------
# Recommended using functools.wraps from comment:
# https://stackoverflow.com/a/739665/4970632
# This tool preserve __name__ metadata.
# Builtin module requirements
import os
import re
import numpy as np
import warnings
import time
try:
    from icecream import ic
except ImportError:  # graceful fallback if IceCream isn't installed.
    ic = lambda *a: None if not a else (a[0] if len(a) == 1 else a) # noqa
from matplotlib.cbook import mplDeprecation
from matplotlib.projections import register_projection, PolarAxes
from string import ascii_lowercase
from functools import wraps
from inspect import cleandoc
import matplotlib.pyplot as plt
import matplotlib.figure as mfigure
import matplotlib.axes as maxes
import matplotlib.path as mpath
import matplotlib.contour as mcontour
import matplotlib.patheffects as mpatheffects
import matplotlib.dates as mdates
import matplotlib.colors as mcolors
import matplotlib.text as mtext
import matplotlib.ticker as mticker
import matplotlib.artist as martist
import matplotlib.transforms as mtransforms
import matplotlib.collections as mcollections
# Local modules, projection sand formatters and stuff
from .gridspec import _gridspec_kwargs, FlexibleGridSpecFromSubplotSpec
from .rcmod import rc, rc_context
from .axis import Scale, Locator, Formatter # default axis norm and formatter
from .proj import Aitoff, Hammer, KavrayskiyVII, WinkelTripel
from . import colortools
from . import utils
from .utils import dot_dict, fill
rc_context_rcmod = rc_context # so it won't be overritten by method declarations in subclasses

# Filter warnings, seems to be necessary before drawing stuff for first time,
# otherwise this has no effect (e.g. if you stick it in a function)
warnings.filterwarnings('ignore', category=mplDeprecation)
# Optionally import mapping toolboxes
# Main conda distro says they are incompatible, so make sure not required!
try:
    import mpl_toolkits.basemap as mbasemap
except ModuleNotFoundError:
    pass
try:
    from cartopy.mpl.geoaxes import GeoAxes
    from cartopy.crs import PlateCarree
    PlateCarree = PlateCarree() # global variable
except ModuleNotFoundError:
    GeoAxes = PlateCarree = object

# Global variables
# These are used to bulk wrap a bunch of axes methods
# NOTE: The below are used for cmap
_line_methods = ( # basemap methods you want to wrap that aren't 2D grids
    'plot', 'scatter'
    )
_edge_methods = (
    'pcolor', 'pcolorpoly', 'pcolormesh',
    )
_center_methods = (
    'contour', 'contourf', 'quiver', 'streamplot', 'barbs',
    )
_contour_methods = (
    'contour', 'contourf',
    )
_pcolor_methods = (
    'pcolor', 'pcolormesh', 'pcolorpoly'
    )
_nolevels_methods = (
    'pcolor', 'pcolormesh', 'pcolorpoly', 'imshow', 'matshow', 'spy'
    )
_cycle_methods  = (
    'plot', 'scatter', 'bar', 'barh', 'hist', 'boxplot', 'errorbar'
    )
_cmap_methods = (
    'cmapline',
    'contour', 'contourf', 'pcolor', 'pcolormesh',
    'matshow', 'imshow', 'spy', 'hist2d'
    )
_disabled_methods = {
    "Unsupported plotting function {}.":
        ('pie', 'table', 'hexbin', 'eventplot',
        'triplot', 'tricontour', 'tricontourf', 'tripcolor',
        'xcorr', 'acorr', 'psd', 'csd', 'magnitude_spectrum',
        'angle_spectrum', 'phase_spectrum', 'cohere', 'specgram'),
    "Redundant function {} has been disabled.":
        ('plot_date', 'semilogx', 'semilogy', 'loglog'),
    "Redundant function {} has been disabled. Just use projection='polar' instead.":
        ('polar',)
    }
_map_disabled_methods = (
    'matshow', 'imshow', 'spy', 'bar', 'barh',
    'hist', 'hist2d', 'errorbar', 'boxplot', 'violinplot', 'step', 'stem',
    'hlines', 'vlines', 'axhline', 'axvline', 'axhspan', 'axvspan',
    'fill_between', 'fill_betweenx', 'fill', 'stackplot')

#------------------------------------------------------------------------------#
# Create matplotlib.Path objects
#------------------------------------------------------------------------------#
def circle(N):
    """
    Draw a circle.
    """
    theta = np.linspace(0, 2*np.pi, N)
    center, radius = [0.5, 0.5], 0.5
    verts = np.vstack([np.sin(theta), np.cos(theta)]).T
    return mpath.Path(verts * radius + center)

#------------------------------------------------------------------------------#
# Misc tools
#------------------------------------------------------------------------------#
def docstring_fix(child):
    """
    Decorator function for appending documentation from overridden method
    onto the overriding method docstring.
    Adapted from: https://stackoverflow.com/a/8101598/4970632
    """
    for name,chfunc in vars(child).items(): # returns __dict__ object
        if not callable(chfunc): # better! see: https://stackoverflow.com/a/624939/4970632
        # if not isinstance(chfunc, FunctionType):
            continue
        for parent in getattr(child, '__bases__', ()):
            parfunc = getattr(parent, name, None)
            if not getattr(parfunc, '__doc__', None):
                continue
            if not getattr(chfunc, '__doc__', None):
                chfunc.__doc__ = '' # in case it's None
            cmessage = f'Full name: {parfunc.__qualname__}()'
            pmessage = f'Parent method (documentation below): {chfunc.__qualname__}()'
            chfunc.__doc__ = f'\n{cmessage}\n{cleandoc(chfunc.__doc__)}\n{pmessage}\n{cleandoc(parfunc.__doc__)}'
            break # only do this for the first parent class
    return child

def fancy_decorator(decorator):
    """
    Normally to make a decorator that accepts arguments, you have to create
    3 nested function definitions. This abstracts that away -- if you decorate
    your decorator-function declaration with this, the decorator will now accept arguments.
    See: https://stackoverflow.com/a/1594484/4970632
    """
    @wraps(decorator)
    def decorator_maker(*args, **kwargs):
        def decorator_wrapper(func):
            return decorator(func, *args, **kwargs)
        return decorator_wrapper
    return decorator_maker

def timer(func):
    """
    A decorator that prints the time a function takes to execute.
    See: https://stackoverflow.com/a/1594484/4970632
    """
    @wraps(func)
    def decorator(*args, **kwargs):
        t = time.clock()
        res = func(*args, **kwargs)
        print(f'{func.__name__} time: {time.clock()-t}s')
        return res
    return decorator

def logger(func):
    """
    A decorator that logs the activity of the script (it actually just prints it,
    but it could be logging!)
    See: https://stackoverflow.com/a/1594484/4970632
    """
    @wraps(func)
    def decorator(*args, **kwargs):
        res = func(*args, **kwargs)
        print(f'{func.__name__} called with: {args} {kwargs}')
        return res
    return decorator

def counter(func):
    """
    A decorator that counts and prints the number of times a function
    has been executed.
    See: https://stackoverflow.com/a/1594484/4970632
    """
    @wraps(func)
    def decorator(*args, **kwargs):
        decorator.count = decorator.count + 1
        res = func(*args, **kwargs)
        print(f'{func.__name__} has been used: {decorator.count}x')
        return res
    decorator.count = 0
    return decorator

#------------------------------------------------------------------------------
# Helper functions for plot overrides
# List of stuff in pcolor/contourf that need to be fixed:
#   * White lines between the edges; cover them by changing edgecolors to 'face'.
#   * Determination of whether we are using graticule edges/centers; not sure
#       what default behavior is but harder to debug. My decorator is nicer.
#   * Pcolor can't take an extend argument, and colorbar can take an extend argument
#       but it is ignored when the mappable is a contourf. Make our pcolor decorator
#       add an "extend" attribute on the mappable that our colorbar decorator detects.
#   * Extend used in contourf causes color-change between in-range values and
#       out-of-range values, while extend used in colorbar on pcolor has no such
#       color change. Standardize by messing with the colormap.
#------------------------------------------------------------------------------
def _parse_args(args):
    """
    Parse arguments for check centers/edges.
    """
    if len(args)>2:
        x, y = args[:2]
        Zs = args[2:]
    else:
        Zs = args
        x = np.arange(Zs[0].shape[0])
        y = np.arange(Zs[0].shape[1])
    Zs = [np.array(Z) for Z in Zs]
    return np.array(x), np.array(y), Zs

def _check_centers(func):
    """
    Check shape of arguments passed to contour, and fix result.
    Optional numbers of arguments:
      * Z
      * U, V
      * x, y, Z
      * x, y, U, V
    """
    @wraps(func)
    def decorator(*args, **kwargs):
        # Checks whether sizes match up, checks whether graticule was input
        x, y, Zs = _parse_args(args)
        xlen, ylen = x.shape[0], y.shape[-1]
        for Z in Zs:
            if Z.shape[0]==xlen-1 and Z.shape[1]==ylen-1:
                x, y = (x[1:]+x[:-1])/2, (y[1:]+y[:-1])/2 # get centers, given edges
            elif Z.shape[0]!=xlen or Z.shape[1]!=ylen:
                raise ValueError(f'X ({"x".join(str(i) for i in x.shape)}) '
                        f'and Y ({"x".join(str(i) for i in y.shape)}) must correspond to '
                        f'nrows ({Z.shape[0]}) and ncolumns ({Z.shape[1]}) of Z, or its borders.')
        Zs = [Z.T for Z in Zs]
        result = func(x, y, *Zs, **kwargs)
        return result
    return decorator

def _check_edges(func):
    """
    Check shape of arguments passed to pcolor, and fix result.
    """
    @wraps(func)
    def decorator(*args, **kwargs):
        # Checks that sizes match up, checks whether graticule was input
        x, y, Zs = _parse_args(args)
        xlen, ylen = x.shape[0], y.shape[-1]
        for Z in Zs:
            if Z.shape[0]==xlen and Z.shape[1]==ylen:
                x, y = utils.edges(x), utils.edges(y)
            elif Z.shape[0]!=xlen-1 or Z.shape[1]!=ylen-1:
                raise ValueError(f'X ({"x".join(str(i) for i in x.shape)}) '
                        f'and Y ({"x".join(str(i) for i in y.shape)}) must correspond to '
                        f'nrows ({Z.shape[0]}) and ncolumns ({Z.shape[1]}) of Z, or its borders.')
        Zs = [Z.T for Z in Zs]
        result = func(x, y, *Zs, **kwargs)
        return result
        # return func(self, x, y, *Zs, **kwargs)
    return decorator

def _cycle_features(self, func):
    """
    Allow specification of color cycler at plot-time. Will simply set the axes
    property cycler, and if it differs from user input, update it.
    See: https://github.com/matplotlib/matplotlib/blob/master/lib/matplotlib/axes/_base.py
    The set_prop_cycle command modifies underlying _get_lines and _get_patches_for_fill.
    """
    @wraps(func)
    def decorator(*args, cycle=None, **kwargs):
        # Determine and temporarily set cycler
        if cycle is not None:
            if utils.isscalar(cycle):
                cycle = cycle,
            cycle = colortools.Cycle(*cycle)
            self.set_prop_cycle(color=cycle)
        return func(*args, **kwargs)
    return decorator

def _cmap_features(self, func):
    """
    Manage output of contour and pcolor functions.
    New features:
        * Create new colormaps on the fly, and merge arbitrary named
          or created colormaps.
        * Always use full range of colormap, whether you are extending
          max, min, neither, or both. For the first three, will reconstruct
          colormap so 'out-of-bounds' have same color as edge colors
          from 'in-bounds' region.
    Also see: https://stackoverflow.com/a/48614231/4970632
    """
    @wraps(func)
    def decorator(*args, cmap=None, cmap_kw={},
                resample=False, levels=None, extremes=True, norm=None,
                extend='neither', **kwargs):
        # NOTE: We will normalize the data with whatever is passed, e.g.
        # logarithmic or whatever
        # is passed to Norm
        # Call function with special args removed
        name = func.__name__
        levels = utils.fill(levels, 11)
        contour_kw = {}
        if name in _contour_methods: # only valid kwargs for contouring
            contour_kw = {'levels': levels, 'extend': extend}
        if norm:
            contour_kw['norm'] = colortools.Norm(norm)
        result = func(*args, norm=norm, **contour_kw, **kwargs)
        if name in _nolevels_methods:
            result.extend = extend

        # Get levels automatically determined by contourf, or make them
        # from the automatically chosen pcolor/imshow clims
        if not utils.isvector(levels):
            if hasattr(result, 'levels'):
                levels = result.levels
            else:
                levels = np.linspace(*result.get_clim(), levels)

        # Choose to either:
        # 1) Use len(levels) lookup table values and a smooth normalizer
        if resample:
            N = len(levels)
            norm = colortools.LinearSegmentedNorm(norm=norm, levels=levels)
        # 2) Use a high-resolution lookup table with a discrete normalizer
        # NOTE: Unclear which is better/more accurate? Intuition is this one.
        # Will bin physical values into len(levels)-1 bins (plus, optionally,
        # bins for extremes -- the 'extend' kwarg controls this).
        else:
            N = None # will be ignored
            norm = colortools.BinNorm(norm=norm, levels=levels, extend=extend)
        result.set_norm(norm)

        # Specify colormap
        cmap = cmap or rc['image.cmap']
        if isinstance(cmap, (str,dict,mcolors.Colormap)):
            cmap = cmap, # make a tuple
        cmap = colortools.Colormap(*cmap, N=N, extend=extend, **cmap_kw)
        if not cmap._isinit:
            cmap._init()
        result.set_cmap(cmap)

        # Fix resulting colorbar for 'cmapline's
        if name=='cmapline':
            if levels is None:
                levels = np.sort(np.unique(result.get_array()))
            result = self.contourf([0,0], [0,0], np.nan*np.ones((2,2)),
                cmap=cmap, levels=levels, norm=norm)

        # Fix white lines between filled contours/mesh
        linewidth = 0.3 # seems to be lowest threshold where white lines disappear
        if name=='contourf':
            for contour in result.collections:
                contour.set_edgecolor('face')
                contour.set_linewidth(linewidth)
        elif name in _pcolor_methods:
            result.set_edgecolor('face')
            result.set_linewidth(linewidth) # seems to do the trick, without dots in corner being visible
        return result
    return decorator

#------------------------------------------------------------------------------#
# Helper functions for basemap and cartopy plot overrides
# NOTE: These wrappers should be invoked *after* _check_centers and _check_edges,
# which perform basic shape checking and permute the data array, so the data
# will now be y by x (or lat by lon) instead of lon by lat.
#------------------------------------------------------------------------------#
# Normally we *cannot* modify the underlying *axes* pcolormesh etc. because this
# this will cause basemap's self.m.pcolormesh etc. to use my *custom* version and
# cause a suite of weird errors. Prevent this recursion with the below decorator.
def _m_call(self, func):
    """
    Call the basemap version of the function of the same name.
    """
    name = func.__name__
    @wraps(func)
    def decorator(*args, **kwargs):
        return self.m.__getattribute__(name)(ax=self, *args, **kwargs)
    return decorator

def _no_recurse(self, func):
    """
    Decorator to prevent recursion in Basemap method overrides.
    See: https://stackoverflow.com/a/37675810/4970632
    """
    @wraps(func)
    # def decorator(self, *args, **kwargs):
    def decorator(*args, **kwargs):
        name = getattr(func, '__name__')
        if self._recurred:
            # Don't call func again, now we want to call the parent function
            # Note this time 'self' is repeated in position args[0]
            self._recurred = False
            result = super(BasemapAxes, self).__getattribute__(name)(*args, **kwargs)
        else:
            # Actually return the basemap version
            self._recurred = True
            # result = self.m.__getattribute__(name)(ax=self, *args, **kwargs)
            result = func(*args, **kwargs)
        self._recurred = False # cleanup, in case recursion never occurred
        return result
    return decorator

def _linefix_basemap(self, func):
    """
    Simply add an additional kwarg. Needs whole function because we
    want to @wrap it to preserve documentation.
    """
    @wraps(func)
    # def decorator(self, *args, **kwargs):
    def decorator(*args, **kwargs):
        kwargs.update(latlon=True)
        return func(*args, **kwargs)
        # return func(self, *args, **kwargs)
    return decorator

def _gridfix_basemap(self, func):
    """
    Interpret coordinates and fix discontinuities in grid.
    """
    @wraps(func)
    def decorator(lon, lat, Z, **kwargs):
    # def decorator(self, lon, lat, Z, **kwargs):
        # Raise errors
        # print('lon', lon, 'lat', lat, 'Z', Z)
        lonmin, lonmax = self.m.lonmin, self.m.lonmax
        if lon.max()>lon.min()+360:
            raise ValueError(f'Longitudes span {lon.min()} to {lon.max()}. Can only span 360 degrees at most.')
        if lon.min()<-360 or lon.max()>360:
            raise ValueError(f'Longitudes span {lon.min()} to {lon.max()}. Must fall in range [-360, 360].')
        if lonmin<-360 or lonmin>0:
            print(f'Warning: Minimum longitude is {lonmin}, not in range [-360,0].')
            # raise ValueError('Minimum longitude must fall in range [-360, 0].')
        # 1) Establish 360-degree range
        lon -= 720
        while True:
            filter_ = lon<lonmin
            if filter_.sum()==0:
                break
            lon[filter_] += 360
        # 2) Roll, accounting for whether ends are identical
        # If go from 0,1,-->,359,0 (borders), returns id of first zero
        roll = -np.argmin(lon) # always returns *first* value
        if lon[0]==lon[-1]:
            lon = np.roll(lon[:-1], roll)
            lon = np.append(lon, lon[0]+360)
        else:
            lon = np.roll(lon, roll)
        Z = np.roll(Z, roll, axis=1)
        # 3) Roll in same direction some more, if some points on right-edge
        # extend more than 360 above the minimum longitude; THEY should be the
        # ones on west/left-hand-side of map
        lonroll = np.where(lon>lonmin+360)[0] # tuple of ids
        if lonroll: # non-empty
            roll = lon.size-min(lonroll) # e.g. if 10 lons, lonmax id is 9, we want to roll once
            lon = np.roll(lon, roll) # need to roll foreward
            Z = np.roll(Z, roll, axis=1) # roll again
            lon[:roll] -= 360 # retains monotonicity
        # 4) Set NaN where data not in range lonmin, lonmax
        # This needs to be done for some regional smaller projections or otherwise
        # might get weird side-effects due to having valid data way outside of the
        # map boundaries -- e.g. strange polygons inside an NaN region
        Z = Z.copy()
        if lon.size-1==Z.shape[1]: # test western/eastern grid cell edges
            # remove data where east boundary is east of min longitude or west
            # boundary is west of max longitude
            Z[:,(lon[1:]<lonmin) | (lon[:-1]>lonmax)] = np.nan
        elif lon.size==Z.shape[1]: # test the centers
            # this just tests centers and pads by one for safety
            # remember that a *slice* with no valid range just returns empty array
            where = np.where((lon<lonmin) | (lon>lonmax))[0]
            Z[:,where[1:-1]] = np.nan
        # 5) Fix holes over poles by interpolating there (equivalent to
        # simple mean of highest/lowest latitude points)
        if lon.size==Z.shape[1]: # have centers, not grid cell edges
            Z_south = np.repeat(Z[0,:].mean(),  Z.shape[1])[None,:]
            Z_north = np.repeat(Z[-1,:].mean(), Z.shape[1])[None,:]
            lat = np.concatenate(([-90], lat, [90]))
            Z = np.concatenate((Z_south, Z, Z_north), axis=0)
        # 6) Fix seams at map boundary; 3 scenarios here:
        # Have edges (e.g. for pcolor), and they fit perfectly against basemap seams
        # this does not augment size
        if lon[0]==lonmin and lon.size-1==Z.shape[1]: # borders fit perfectly
            pass # do nothing
        # Have edges (e.g. for pcolor), and the projection edge is in-between grid cell boundaries
        # this augments size by 1
        elif lon.size-1==Z.shape[1]: # no interpolation necessary; just make a new grid cell
            lon = np.append(lonmin, lon) # append way easier than concatenate
            lon[-1] = lonmin + 360 # we've added a new tiny cell to the end
            Z = np.concatenate((Z[:,-1:], Z), axis=1) # don't use pad; it messes up masked arrays
        # Have centers (e.g. for contourf), and we need to interpolate to the
        # left/right edges of the map boundary
        # this augments size by 2
        elif lon.size==Z.shape[1]: # linearly interpolate to the edges
            x = np.array([lon[-1], lon[0]+360]) # x
            y = np.concatenate((Z[:,-1:], Z[:,:1]), axis=1)
            xq = lonmin+360
            yq = (y[:,:1]*(x[1]-xq) + y[:,1:]*(xq-x[0]))/(x[1]-x[0]) # simple linear interp formula
            Z = np.concatenate((yq, Z, yq), axis=1)
            lon = np.append(np.append(lonmin, lon), lonmin+360)
        else:
            raise ValueError()
        # Finally get grid of x/y map projection coordinates
        lat[lat>90], lat[lat<-90] = 90, -90 # otherwise, weird stuff happens
        x, y = self.m(*np.meshgrid(lon, lat))
        # Prevent error where old boundary, drawn on a different axes, remains
        # to the Basemap instance, which means it is not in self.patches, which
        # means Basemap tries to draw it again so it can clip the contours by the
        # resulting path, which raises error because you can't draw on Artist on multiple axes
        self.m._mapboundarydrawn = self.boundary # stored the axes-specific boundary here
        # Call function
        return func(x, y, Z, **kwargs)
    return decorator

def _linefix_cartopy(func):
    """
    Simply add an additional kwarg. Needs whole function because we
    want to @wrap it to preserve documentation.
    """
    @wraps(func)
    def decorator(*args, **kwargs):
        if not kwargs.get('transform', None):
            kwargs['transform'] = PlateCarree
        return func(*args, **kwargs)
    return decorator

def _gridfix_cartopy(func):
    """
    Apply default transform and fix discontinuities in grid.
    """
    @wraps(func)
    def decorator(lon, lat, Z, transform=PlateCarree, **kwargs):
        # The todo list for cartopy is much shorter, as we don't have to worry
        # about longitudes going from 0 to 360, -180 to 180, etc.; projection handles all that
        # 1) Fix holes over poles by *interpolating* there (equivalent to
        # simple mean of highest/lowest latitude points)
        Z_south = np.repeat(Z[0,:].mean(),  Z.shape[1])[None,:]
        Z_north = np.repeat(Z[-1,:].mean(), Z.shape[1])[None,:]
        lat = np.concatenate(([-90], lat, [90]))
        Z = np.concatenate((Z_south, Z, Z_north), axis=0)
        # 2) Fix seams at map boundary; this time the fancy projection will
        # handle issues with pcolor seams that we'd have with basemap, but still
        # have to ensure *circular* coverage if doing e.g. contourf
        lon = np.array((*lon, lon[0]+360)) # make longitudes circular
        Z = np.concatenate((Z, Z[:,:1]), axis=1) # make data circular
        # Call function
        # _ = io.StringIO() # message has a bunch of unnecessary newlines; will modify it
        # with redirect_stdout(_):
        # with warnings.catch_warnings():
        #     warnings.simplefilter('ignore')
        result = func(lon, lat, Z, transform=transform, **kwargs)
        # Call function
        return result
    return decorator

#------------------------------------------------------------------------------
# Custom figure class
#------------------------------------------------------------------------------
class EmptyPanel(object):
    """
    Dummy object to put in place when an axes or figure panel does not exist.
    Makes nicer error message than if we just put 'None' or nothing there.
    Remember: __getattr__ is invoked only when __getattribute__ fails, i.e.
    when user requests anything that isn't a hidden object() method.
    """
    def __bool__(self):
        return False # it's empty, so this is 'falsey'

    def __getattr__(self, attr, *args):
        raise NotImplementedError('Panel does not exist.')

@docstring_fix
class Figure(mfigure.Figure):
    """
    Subclass of the mfigure.Figure class, with lots of special formatting
    options. Can be called by using pyplot.figure(FigureClass=Figure) kwargument
    in my subplots function.

    Features
    --------
    Need to document features.
        rcreset (True):
            when figure is drawn, reset rc settings to defaults?
        tight (True):
    """
    def __init__(self, figsize,
            gridspec=None, subplots_kw=None,
            rcreset=True, tight=True, pad=0.1,
            **kwargs):
        """
        Matplotlib figure with some pizzazz.
        Requires:
            figsize:
                figure size (width, height) in inches
            subplots_kw:
                dictionary-like container of the keyword arguments used to
                initialize
        Optional:
            rcreset (True):
                when figure is drawn, reset rc settings to defaults?
            tight (True):
                when figure is drawn, trim the gridspec edges without messing
                up axes aspect ratios and internal spacing?
        """
        # Initialize figure with some custom attributes.
        # Whether to reset rcParams wheenver a figure is drawn (e.g. after
        # ipython notebook finishes executing)
        self._rcreset  = rcreset
        self._smart_pad = pad
        self._smart_tight = tight # note name _tight already taken!
        self._smart_tight_init = True # is figure in its initial state?
        # Gridspec information
        self._gridspec = gridspec # gridspec encompassing drawing area
        self._subplots_kw = dot_dict(subplots_kw) # extra special settings
        # Figure dimensions
        self.width  = figsize[0] # dimensions
        self.height = figsize[1]
        # Panels, initiate as empty
        self.leftpanel   = EmptyPanel()
        self.bottompanel = EmptyPanel()
        self.rightpanel  = EmptyPanel()
        self.toppanel    = EmptyPanel()
        # Proceed
        super().__init__(figsize=figsize, **kwargs) # python 3 only

    def _rowlabels(self, labels, **kwargs):
        # Assign rowlabels
        axs = []
        for ax in self.axes:
            if isinstance(ax, BaseAxes) and not isinstance(ax, PanelAxes) and ax.cols[0]==0:
                axs.append(ax)
        if isinstance(labels,str): # common during testing
            labels = [labels]*len(axs)
        if len(labels)!=len(axs):
            raise ValueError(f'Got {len(labels)} labels, but there are {len(axs)} rows.')
        axs = [ax for _,ax in sorted(zip([ax.rows[0] for ax in axs],axs))]
        for ax,label in zip(axs,labels):
            if label and not ax.rowlabel.get_text():
                # Create a CompositeTransform that converts coordinates to
                # universal dots, then back to axes
                label_to_ax = ax.yaxis.label.get_transform() + ax.transAxes.inverted()
                x, _ = label_to_ax.transform(ax.yaxis.label.get_position())
                ax.rowlabel.set_visible(True)
                # Add text
                ax.rowlabel.update({'text':label, 'position':[x,0.5],
                    'ha':'right', 'va':'center', **kwargs})

    def _collabels(self, labels, **kwargs):
        # Assign collabels
        axs = []
        for ax in self.axes:
            if isinstance(ax, BaseAxes) and not isinstance(ax, PanelAxes) and ax.rows[0]==0:
                axs.append(ax)
        if isinstance(labels,str):
            labels = [labels]*len(axs)
        if len(labels)!=len(axs):
            raise ValueError(f'Got {len(labels)} labels, but there are {len(axs)} columns.')
        axs = [ax for _,ax in sorted(zip([ax.cols[0] for ax in axs],axs))]
        for ax,label in zip(axs,labels):
            if label and not ax.collabel.get_text():
                ax.collabel.update({'text':label, **kwargs})

    def _suptitle_setup(self, offset=False, **kwargs):
        # Intelligently determine supertitle position:
        # 1) Determine x by the underlying gridspec structure, where main axes lie.
        # 2) Determine y by whether titles exist on top-row axes.
        # NOTE: Default linespacing is 1.2; it has no get, only a setter; see
        # https://matplotlib.org/api/text_api.html#matplotlib.text.Text.set_linespacing
        if not hasattr(self,'_suptitle') or self._suptitle is None:
            self.suptitle('')
        title_height = self.axes[0].title.get_size()/72
        line_spacing = self.axes[0].title._linespacing
        base = rc['axes.titlepad']/72 + self._gridspec.top*self.height
        left = self._subplots_kw.left
        right = self._subplots_kw.right
        if self.leftpanel:
            left += (self._subplots_kw.lwidth + self._subplots_kw.lspace)
        if self.rightpanel:
            right += (self._subplots_kw.rwidth + self._subplots_kw.rspace)
        xpos = left/self.width + 0.5*(self.width - left - right)/self.width
        if offset:
            offset = line_spacing*title_height
        else:
            offset = 0
        ypos = (base + offset)/self.height
        self._suptitle.update({'position':(xpos, ypos), 'ha':'center', 'va':'bottom', **kwargs})

    def draw(self, *args, **kwargs):
        # Special: Figure out if other titles are present, and if not
        # bring suptitle close to center
        offset = False
        for ax in self.axes:
            if isinstance(ax, BaseAxes) and ax.rows[0]==0 \
                and ((ax.title.get_text() and not ax._title_inside)
                or ax.collabel.get_text()):
                offset = True
                break
        self._suptitle_setup(offset=offset) # just applies the spacing
        # If rc settings have been changed, reset them when the figure is
        # displayed (usually means we have finished executing a notebook cell).
        if not rc._init and self._rcreset:
            print('Resetting rcparams.')
            rc.reset()
        # If we haven't already, compress edges
        # NOTE: Currently for cartopy axes with non-global edges, this can
        # erroneously identify invisible edges of map as being part of boundary
        # if self._smart_tight_init and self._smart_tight and \
        #     not any(isinstance(ax, MapAxes) for ax in self.axes):
        if self._smart_tight_init and self._smart_tight:
            print('Adjusting gridspec.')
            self.smart_tight_layout()
        return super().draw(*args, **kwargs)

    def panel_factory(self, subspec, whichpanels=None,
            hspace=None, wspace=None, hwidth=None, wwidth=None,
            **kwargs):
        # Helper function for creating paneled axes.
        width, height = self.width, self.height
        translate = {'bottom':'b', 'top':'t', 'right':'r', 'left':'l'}
        whichpanels = translate.get(whichpanels, whichpanels)
        whichpanels = whichpanels or 'r'
        hspace = utils.fill(hspace, 0.13) # teeny space
        wspace = utils.fill(wspace, 0.13)
        hwidth = utils.fill(hwidth, 0.3) # default is panels for plotting stuff, not colorbars
        wwidth = utils.fill(wwidth, 0.3)
        if any(s.lower() not in 'lrbt' for s in whichpanels):
            raise ValueError(f'Whichpanels argument can contain characters l (left), r (right), b (bottom), or t (top), instead got "{whichpanels}".')

        # Determine rows/columns and indices
        nrows = 1 + sum(1 for i in whichpanels if i in 'bt')
        ncols = 1 + sum(1 for i in whichpanels if i in 'lr')
        sides_lr = [l for l in ['l',None,'r'] if not l or l in whichpanels]
        sides_tb = [l for l in ['t',None,'b'] if not l or l in whichpanels]
        # Detect empty positions and main axes position
        main_pos  = (int('t' in whichpanels), int('l' in whichpanels))
        corners   = {'tl':(0,0),             'tr':(0,main_pos[1]+1),
                     'bl':(main_pos[0]+1,0), 'br':(main_pos[0]+1,main_pos[1]+1)}
        empty_pos = [position for corner,position in corners.items() if
                     corner[0] in whichpanels and corner[1] in whichpanels]

        # Fix wspace/hspace in inches, using the Bbox from get_postition
        # on the subspec object to determine physical width of axes to be created
        # * Consider writing some convenience funcs to automate this unit conversion
        bbox = subspec.get_position(self) # valid since axes not drawn yet
        if hspace is not None:
            height = np.diff(bbox.intervaly)[0]*height - hspace*(nrows-1)
            hspace = hspace/(height/nrows)
        if wspace is not None:
            width = np.diff(bbox.intervalx)[0]*width - wspace*(ncols-1)
            wspace = wspace/(width/ncols)

        # Figure out hratios/wratios
        # Will enforce (main_width + panel_width)/total_width = 1
        wwidth_ratios = [width-wwidth*(ncols-1)]*ncols
        if wwidth_ratios[0]<0:
            raise ValueError(f'Panel wwidth is too large. Must be less than {width/(nrows-1):.3f}.')
        for i in range(ncols):
            if i!=main_pos[1]: # this is a panel entry
                wwidth_ratios[i] = wwidth
        hwidth_ratios = [height-hwidth*(nrows-1)]*nrows
        if hwidth_ratios[0]<0:
            raise ValueError(f'Panel hwidth is too large. Must be less than {height/(ncols-1):.3f}.')
        for i in range(nrows):
            if i!=main_pos[0]: # this is a panel entry
                hwidth_ratios[i] = hwidth

        # Create subplotspec and draw the axes
        # Will create axes in order of rows/columns so that the "base" axes
        # are always built before the axes to be "shared" with them
        panels = []
        sharex_outside = kwargs.pop('sharex', None) # we do this ourselves
        sharey_outside = kwargs.pop('sharey', None)
        gs = FlexibleGridSpecFromSubplotSpec(
                nrows         = nrows,
                ncols         = ncols,
                subplot_spec  = subspec,
                wspace        = wspace,
                hspace        = hspace,
                width_ratios  = wwidth_ratios,
                height_ratios = hwidth_ratios,
                )
        # Draw main axes
        ax = self.add_subplot(gs[main_pos[0], main_pos[1]], **kwargs)
        axmain = ax
        # Draw axes
        panels = {}
        kwpanels = {**kwargs, 'projection':'panel'} # override projection
        kwpanels.pop('number', None) # don't want numbering on panels
        translate = {'b':'bottom', 't':'top', 'l':'left', 'r':'right'} # inverse
        for r,side_tb in enumerate(sides_tb): # iterate top-bottom
            for c,side_lr in enumerate(sides_lr): # iterate left-right
                if (r,c) in empty_pos or (r,c)==main_pos:
                    continue
                side = translate.get(side_tb or side_lr, None)
                ax = self.add_subplot(gs[r,c], panelside=side, panelparent=axmain, **kwpanels)
                panels[side] = ax

        # Finally add as attributes, and set up axes sharing
        # In subplots() script, need to run _panel_setup() after spanning
        # axes are drawn, so comment out to avoid calling it twice
        axmain.bottompanel = panels.get('bottom', None)
        axmain.toppanel    = panels.get('top', None)
        axmain.leftpanel   = panels.get('left', None)
        axmain.rightpanel  = panels.get('right', None)
        # axmain._panel_setup() # TODO: don't know why commenting this out doens't mess things up
        axmain._sharex_setup(sharex_outside)
        axmain._sharey_setup(sharey_outside)
        return axmain

    def smart_tight_layout(self, adjust=True, silent=False, update=True, pad=None):
        """
        Get arguments necessary passed to subplots() to create a tight figure
        bounding box without screwing aspect ratios, widths/heights, and such.
        """
        # Get bounding box that encompasses *all artists*, compare to bounding
        # box used for saving *figure*
        if pad is None:
            pad = self._smart_pad
        if self._subplots_kw is None or self._gridspec is None:
            raise ValueError("Initialize figure with 'subplots_kw' and 'gridspec' to draw tight grid.")
        obbox = self.bbox_inches # original bbox
        bbox = self.get_tightbbox(self.canvas.get_renderer())
        ox, oy, x, y = obbox.intervalx, obbox.intervaly, bbox.intervalx, bbox.intervaly
        x1, y1, x2, y2 = x[0], y[0], ox[1]-x[1], oy[1]-y[1] # deltas
        # width, height = ox[1], oy[1] # desired save-width

        # Apply new settings
        lname = 'lspace' if self.leftpanel else 'left'
        rname = 'rspace' if self.rightpanel else 'right'
        bname = 'bspace' if self.bottompanel else 'bottom'
        tname = 'top'
        subplots_kw = self._subplots_kw
        left   = getattr(subplots_kw, lname) - x1 + pad
        right  = getattr(subplots_kw, rname) - x2 + pad
        bottom = getattr(subplots_kw, bname) - y1 + pad
        top    = getattr(subplots_kw, tname) - y2 + pad
        subplots_kw.update({lname:left, rname:right, bname:bottom, tname:top})
        figsize, *_, gridspec_kw = _gridspec_kwargs(**subplots_kw)
        self._smart_tight_init = False
        self._gridspec.update(**gridspec_kw)
        self.set_size_inches(figsize)

    @timer
    def save(self, filename, adjust=False, silent=False, tight=False, pad=0.1, **kwargs):
        # Notes:
        # * Gridspec object must be updated before figure is printed to
        #     screen in interactive environment; will fail to update after that.
        #     Seems to be glitch, should open thread on GitHub.
        # * To color axes patches, you may have to explicitly pass the
        #     transparent=False kwarg.
        #     Some kwarg translations, to pass to savefig
        if 'alpha' in kwargs:
            kwargs['transparent'] = not bool(kwargs.pop('alpha')) # 1 is non-transparent
        if 'color' in kwargs:
            kwargs['facecolor'] = kwargs.pop('color') # the color
        if tight:
            self.smart_tight_layout()
        # Finally, save
        if not silent:
            print(f'Saving to "{filename}".')
        return super().savefig(os.path.expanduser(filename), **kwargs) # specify DPI for embedded raster objects

    def savefig(*args, **kwargs):
        # Alias for save.
        return self.save(*args, **kwargs)

#------------------------------------------------------------------------------#
# Generalized custom axes class
#------------------------------------------------------------------------------#
@docstring_fix
class BaseAxes(maxes.Axes):
    """
    Subclass the default Axes class. Then register it as the 'base' projection,
    and you will get a subclass Subplot by calling fig.add_subplot(projection='pubplot').
    Notes:
    * You cannot subclass SubplotBase directly, should only be done with
      maxes.subplot_class_factory, which is called automatically when using add_subplot.
    * Cartopy projections should use same methods as for ordinary 'cartesian'
      plot, so we put a bunch of definition overrides in here.
    """
    # Initial stuff
    name = 'base'
    def __init__(self, *args, number=None,
            sharex=None,      sharey=None,
            spanx_group=None, spany_group=None,
            panelparent=None, panelside=None,
            **kwargs):
        # Initialize
        self._spanx = None # always must be present
        self._spany = None
        self._spanx_group = []
        self._spany_group = []
        self._title_inside = False # toggle this to figure out whether we need to push 'super title' up
        super().__init__(*args, **kwargs)

        # Add special row/column labels (can only be filled with text if axes
        # is on leftmost column/topmost row)
        self.collabel = self.text(*self.title.get_position(), '',
                weight=rc['axes.titleweight'], size=rc['axes.titlesize'],
                va='baseline', ha='center', transform=self.title.get_transform())
        self.rowlabel = self.text(*self.yaxis.label.get_position(), '',
                weight=rc['axes.titleweight'], size=rc['axes.titlesize'],
                va='center', ha='right', transform=self.transAxes)

        # Panels
        if panelside not in (None, 'left','right','bottom','top'):
            raise ValueError(f'Invalid panel side "{panelside}".')
        self.panelparent = panelparent # used when declaring parent
        self.panelside = panelside
        self.bottompanel = EmptyPanel()
        self.toppanel    = EmptyPanel()
        self.leftpanel   = EmptyPanel()
        self.rightpanel  = EmptyPanel()

        # Number and size
        subspec = self.get_subplotspec()
        nrows, ncols = subspec.get_gridspec().get_geometry()
        self.rows = (subspec.num1 // ncols, subspec.num2 // ncols)
        self.cols = (subspec.num1 % ncols,  subspec.num2 % ncols)
        self.number = number # for abc numbering
        self.width  = np.diff(self._position.intervalx)*self.figure.width # position is in figure units
        self.height = np.diff(self._position.intervaly)*self.figure.height

        # Turn off tick labels and axis label for shared axes
        # Want to do this ***manually*** because want to have the ability to
        # add shared axes ***after the fact in general***. If the API changes,
        # will modify the below methods.
        if sharex:
            self._sharex_setup(sharex)
        if sharey:
            self._sharey_setup(sharey)

        # Custom idea of 'spanning axes', where x/y axis labels are shared
        # Also make sure always has attribute
        if spanx_group:
            self._spanx_setup(spanx_group)
        if spany_group:
            self._spany_setup(spany_group)

        # Re-enforce rc settings (we may have customized versions, e.g. for
        # CartopyAxes, that __init__ did not configure)
        if not hasattr(self, 'abc'): # add custom property
            self.abc = self.text(0, 0, '')
        self._rcupdate()

    # Apply some simple featueres, and disable spectral and triangular features
    # See: https://stackoverflow.com/a/23126260/4970632
    # Also see: https://github.com/matplotlib/matplotlib/blob/master/lib/matplotlib/axes/_axes.py
    # for all Axes methods ordered logically in class declaration.
    def __getattribute__(self, attr, *args):
        for message,attrs in _disabled_methods.items():
            if attr in attrs:
                raise NotImplementedError(message.format(attr))
        if attr=='pcolorpoly':
            attr = 'pcolor' # use alias so don't run into recursion issues due to internal pcolormesh calls to pcolor()
        obj = super().__getattribute__(attr, *args)
        if attr in _cmap_methods:
            obj = _cmap_features(self, obj)
        elif attr in _cycle_methods:
            obj = _cycle_features(self, obj)
        return obj

    def _spanx_setup(self, group):
        # Specify x, y transform in Figure coordinates
        self.xaxis.label.set_transform(mtransforms.blended_transform_factory(
                self.figure.transFigure, mtransforms.IdentityTransform()
                ))
        # Get min/max positions, in figure coordinates, of spanning axes
        xmin = min(ax.get_position().xmin for ax in group)
        xmax = max(ax.get_position().xmax for ax in group)
        self.xaxis.label.set_position(((xmin+xmax)/2, 0))
        # Add attribute for reference, and make this label invisible
        for ax in group:
            ax._spanx = self # may be self!
            ax._spanx_group = group
            if ax is not self:
                ax.xaxis.label.set_visible(False)
            else:
                # TODO: Delete this, was just useful for bug-fixing
                ax.xaxis.label.set_visible(True)

    def _spany_setup(self, group):
        # Specify x, y transform in Figure coordinates
        # self.text(0.5,0.5,'This is a spanning axis!')
        self.yaxis.label.set_transform(mtransforms.blended_transform_factory(
                    mtransforms.IdentityTransform(), self.figure.transFigure
                    ))
        # Get min/max positions, in figure coordinates, of spanning axes
        ymin = min(ax.get_position().ymin for ax in group)
        ymax = max(ax.get_position().ymax for ax in group)
        self.yaxis.label.set_position((0, (ymin+ymax)/2))
        # Add attribute for reference, and make this label invisible
        for ax in group:
            ax._spany = self # may say self._spany = self!
            ax._spany_group = group
            if ax is not self:
                ax.yaxis.label.set_visible(True)

    def _sharex_setup(self, sharex):
        # Share vertical panel x-axes with eachother
        if sharex is None:
            return
        if self is sharex:
            return
        if self.leftpanel and sharex.leftpanel:
            self.leftpanel._sharex_setup(sharex.leftpanel)
        if self.rightpanel and sharex.rightpanel:
            self.rightpanel._sharex_setup(sharex.rightpanel)
        # Share horizontal panel x-axes with sharex
        if self.bottompanel and sharex is not self.bottompanel:
            # print('bottompanel sharing triggered')
            # self.text(0.5, 0.5, f'sharing axes {sharex.number} with {self.number}', ha='center', va='center')
            self.bottompanel._sharex_setup(sharex)
        if self.toppanel and sharex is not self.toppanel:
            self.toppanel._sharex_setup(sharex)
        # Builtin features
        self._sharex = sharex
        self._shared_x_axes.join(self, sharex)
        # Simple method for setting up shared axes
        # WARNING: It turned out setting *another axes' axis label* as
        # this attribute caused error, because matplotlib tried to add
        # the same artist instance twice. Can only make it invisible.
        for t in self.xaxis.get_ticklabels():
            t.set_visible(False)
        self.xaxis.label.set_visible(False)

    def _sharey_setup(self, sharey):
        # Share horizontal panel y-axes with eachother
        if sharey is None:
            return
        if self is sharey:
            return
            # raise ValueError('Cannot share an axes with itself.')
        if self.bottompanel and sharey.bottompanel:
            self.bottompanel._sharey_setup(sharey.bottompanel)
        if self.toppanel and sharey.toppanel:
            self.toppanel._sharey_setup(sharey.toppanel)
        # Share vertical panel y-axes with sharey
        if self.leftpanel:
            self.leftpanel._sharey_setup(sharey)
        if self.rightpanel:
            self.rightpanel._sharey_setup(sharey)
            # sharey = self.leftpanel._sharey or self.leftpanel
        # Builtin features
        self._sharey = sharey
        self._shared_y_axes.join(self, sharey)
        # Simple method for setting up shared axes
        for t in self.yaxis.get_ticklabels():
            t.set_visible(False)
        self.yaxis.label.set_visible(False)

    def _panel_setup(self):
        # Call this once panels are all declared
        # First fix the sharex/sharey settings
        if self.bottompanel:
            self._sharex_setup(self.bottompanel)
        if self.leftpanel:
            self._sharey_setup(self.leftpanel)
        bottom = self.bottompanel or self
        left = self.leftpanel or self
        if self.toppanel:
            self.toppanel._sharex_setup(bottom)
        if self.rightpanel:
            self.rightpanel._sharex_setup(left)
        # Next fix the spanx/spany settings
        # WARNING: If some axes have panels and some don't, this may cause
        # some weird stuff to happen
        if self.bottompanel and self._spanx_group:
            self.bottompanel._spanx_setup([ax.bottompanel for ax in self._spanx_group if ax.bottompanel is not None])
        if self.leftpanel and self._spany_group:
            self.leftpanel._spany_setup([ax.leftpanel for ax in self._spany_group if ax.leftpanel is not None])

    def _rcupdate(self):
        # Update the titling settings
        self.title.update(dict(fontsize=rc['axes.titlesize'], weight=rc['axes.titleweight']))
        if hasattr(self,'_suptitle'):
            self._suptitle.update(dict(fontsize=rc['figure.titlesize'], weight=rc['figure.titleweight']))
        if hasattr(self,'abc'):
            self.abc.update(dict(fontsize=rc['abc.fontsize'], weight=rc['abc.weight']))

    def _title_pos(self, pos, **kwargs):
        # Position arbitrary text to left/middle/right either inside or outside
        # of axes (default is center, outside)
        pad = (rc['axes.titlepad']/72)/self.height # to inches --> to axes relative
        ipad = pad*1.5 # needs a bit more room to look ok
        pos = pos or 'oc'
        if not isinstance(pos, str):
            ha = va = 'center'
            x, y = pos
        else:
            if not any(c in pos for c in 'lcr'):
                pos += 'c'
            if not any(c in pos for c in 'oi'):
                pos += 'o'
            if 'c' in pos:
                x = 0.5
                ha = 'center'
            elif 'l' in pos:
                x = 0 + ipad*('i' in pos)
                ha = 'left'
            elif 'r' in pos:
                x = 1 - ipad*('i' in pos)
                ha = 'right'
            if 'o' in pos:
                y = 1 + pad
                va = 'baseline'
                self._title_inside = False
            elif 'i' in pos:
                y = 1 - ipad
                va = 'top'
            self._title_inside = True
        return {'position':(x,y), 'transform':self.transAxes, 'ha':ha, 'va':va}

    def rc_context(self, *args, **kwargs):
        # Temporarily change rcParams for drawings on this axes.
        return rc_context_rcmod(self, *args, **kwargs)

    # New convenience feature
    # The title position can be a mix of 'l/c/r' and 'i/o'
    def format(self,
        facehatch=None, # control figure/axes background; hatch just applies to axes
        suptitle=None, suptitle_kw={},
        collabels=None, collabels_kw={},
        rowlabels=None, rowlabels_kw={}, # label rows and columns
        title=None, titlepos=None, title_kw={},
        abc=False, abcpos=None, abcformat='', abc_kw={},
        rc_kw={}, **kwargs,
        ):
        """
        Function for formatting axes of all kinds; some arguments are only relevant to special axes, like 
        colorbar or basemap axes. By default, simply applies the dictionary values from settings() above,
        but can supply many kwargs to further modify things.

        Todo
        ----
        * Add options for datetime handling; note possible date axes handles are TimeStamp (pandas),
          np.datetime64, DateTimeIndex; can fix with fig.autofmt_xdate() or manually set options; uses
          ax.is_last_row() or ax.is_first_column(), so should look that up.
        * Problem is there is no autofmt_ydate(), so really should implement my own
          version of this.
        """
        # First update (note that this will call _rcupdate overridden by child
        # classes, which can in turn call the parent class version, so we only
        # need to call this from the base class, and all settings will be applied)
        with self.rc_context(rc_kw, **kwargs):
            self._rcupdate()

        # NOTE: These next two are actually *figure-wide* settings, but that
        # line seems to get blurred -- where we have shared axes, spanning
        # labels, and whatnot. May result in redundant assignments if formatting
        # more than one axes, but operations are fast so some redundancy is nbd.
        # Create figure title
        fig = self.figure # the figure
        if suptitle is not None:
            fig._suptitle_setup(text=suptitle, **suptitle_kw)
        if rowlabels is not None:
            fig._rowlabels(rowlabels, **rowlabels_kw)
        if collabels is not None:
            fig._collabels(collabels, **collabels_kw)

        # Create axes title
        # Input needs to be emptys string
        if title is not None:
            # Allow user to use my *special* text method for
            # making title, e.g. fancy=True
            try:
                self.title.update({'text':title, **title_kw})
            except Exception:
                self.title.set_visible(False)
                self.title = self.text(0, 0, title, **title_kw)
            # Reposition text
            self.title.update(self._title_pos(titlepos or 'oc'))

        # Create axes numbering
        if self.number is not None and abc:
            # Get text
            abcedges = abcformat.split('a')
            text = abcedges[0] + ascii_lowercase[self.number-1] + abcedges[-1]
            abc_kw = {'text':text, 'ha':'left', 'va':'baseline', **abc_kw, **rc['abc']}
            try:
                self.abc.update(abc_kw)
            except Exception:
                self.abc.set_visible(False)
                self.abc = self.text(0, 0, **abc_kw) # call *overridden* text method
            # Reposition text
            self.abc.update(self._title_pos(abcpos or 'ol'))
        elif hasattr(self, 'abc'):
            # Hide
            self.abc.set_visible(False)

    # Create legend creation method
    def legend(self, *args, **kwargs):
        # Call custom legend() function.
        return legend_factory(self, *args, **kwargs)

    # Fill entire axes with colorbar
    def colorbar(self, *args, **kwargs):
        # Call colorbar() function.
        return colorbar_factory(self, *args, **kwargs)

    # Fancy wrappers
    def text(self, x, y, text, transform='axes', fancy=False, black=True,
            linewidth=2, lw=None, **kwarg): # linewidth is for the border
        """
        Wrapper around original text method. Adds feature for easily drawing
        text with white border around black text.
        """
        linewidth = lw or linewidth
        if type(transform) is not str:
            pass # leave alone
            # raise ValueError("Just name the transform with string \"axes\" or \"data\".")
        elif transform=='figure':
            transform = self.figure.transFigure
        elif transform=='axes':
            transform = self.transAxes
        elif transform=='data':
            transform = self.transData
        else:
            raise ValueError("Unknown transform name. Use string \"axes\" or \"data\".")
        t = super().text(x, y, text, transform=transform, **kwarg)
        if fancy:
            fcolor, bcolor = 'wk'[black], 'kw'[black]
            t.update({'color':fcolor, 'zorder':1e10, # have to update after-the-fact for path effects
                'path_effects': [mpatheffects.Stroke(linewidth=linewidth, foreground=bcolor), mpatheffects.Normal()]})
            # t.update({'size':11, 'zorder':1e10,
            #     'path_effects':[mpatheffects.PathPatchEffect(edgecolor=bcolor,linewidth=.6,facecolor=fcolor)]})
        return t

    # @_cycle_features
    def plot(self, *args, cmap=None, values=None, **kwargs):
        """
        Expand functionality of plot to also make LineCollection lines, i.e. lines
        whose colors change as a function of some key/indicator.
        """
        if cmap is None and values is None:
            # Make normal boring lines
            lines = super().plot(*args, **kwargs)
        elif cmap is not None and values is not None:
            # Make special colormap lines
            lines = self.cmapline(*args, cmap=cmap, values=values, **kwargs)
        else:
            # Error
            raise ValueError('To draw colormap line, must provide kwargs "values" and "cmap".')
        return lines

    # @_cycle_features
    def scatter(self, *args, **kwargs):
        """
        Just add some more consistent keyword argument options.
        """
        # Manage input arguments
        if len(args)>4:
            raise ValueError(f'Function accepts up to 4 args, received {len(args)}.')
        args = [*args]
        if len(args)>3:
            kwargs['c'] = args.pop(3)
        if len(args)>2:
            kwargs['s'] = args.pop(2)
        # Apply some aliases for keyword arguments
        aliases = {'c':   ['markercolor', 'color'],
                   's':   ['markersize', 'size'],
            'linewidths': ['lw','linewidth','markeredgewidth', 'markeredgewidths'],
            'edgecolors': ['markeredgecolor', 'markeredgecolors']}
        for name,options in aliases.items():
            for option in options:
                if option in kwargs:
                    kwargs[name] = kwargs.pop(option)
        return super().scatter(*args, **kwargs)

    # @_cmap_features
    def cmapline(self, *args, cmap=None,
            values=None, norm=None,
            bins=True, nbetween=1, **kwargs):
        """
        Create lines with colormap.
        See: https://matplotlib.org/gallery/lines_bars_and_markers/multicolored_line.html
        Will manage input more strictly, this is harder to generalize.
        """
        # First error check
        if len(args) not in (1,2):
            raise ValueError(f'Function requires 1-2 arguments, got {len(args)}.')
        y = np.array(args[-1]).squeeze()
        x = np.arange(y.shape[-1]) if len(args)==1 else np.array(args[0]).squeeze()
        values = np.array(values).squeeze()
        if x.ndim!=1 or y.ndim!=1 or values.ndim!=1:
            raise ValueError(f'Input x ({x.ndim}D), y ({y.ndim}D), and values ({values.ndim}D) must be 1-dimensional.')
        # Next draw the line
        # Interpolate values to optionally allow for smooth gradations between
        # values (bins=False) or color switchover halfway between points (bins=True)
        newx, newy, newvalues = [], [], []
        edges = utils.edges(values)
        if bins:
            norm = colortools.BinNorm(edges)
        else:
            norm = colortools.LinearSegmentedNorm(edges)
        for j in range(y.shape[0]-1):
            newx.extend(np.linspace(x[j], x[j+1], nbetween+2))
            newy.extend(np.linspace(y[j], y[j+1], nbetween+2))
            # WARNING: Below breaks everything! Evidently we need the duplicates
            # if j>0:
            #     interp = interp[1:] # prevent duplicates
            # newvalues.extend(interp)
            # WARNING: Could not get the inverse thing to work properly
            if not isinstance(norm,mcolors.BoundaryNorm):
                # Has inverse
                interp = np.linspace(np.asscalar(norm(values[j])),
                    np.asscalar(norm(values[j+1])), nbetween+2)
                newvalues.extend(norm.inverse(interp))
            else:
                interp = np.linspace(np.asscalar(values[j]),
                    np.asscalar(values[j+1]), nbetween+2)
                newvalues.extend(interp)
        # Create LineCollection and update with values
        newvalues  = np.array(newvalues)
        points     = np.array([newx, newy]).T.reshape(-1, 1, 2) # -1 means value is inferred from size of array, neat!
        segments   = np.concatenate([points[:-1], points[1:]], axis=1)
        collection = mcollections.LineCollection(segments, cmap=cmap, norm=norm, linestyles='-')
        collection.set_array(newvalues)
        collection.update({key:value for key,value in kwargs.items() if key not in ['color']})
        # FIXME: for some reason using 'line' as the mappable results in colorbar
        # with color *cutoffs* at values, instead of centered levels at values
        # line = self.add_collection(collection)
        # line = colortools.mappable(cmap, values, norm=norm) # use hacky mchackerson instead
        self.add_collection(collection)
        return collection

#------------------------------------------------------------------------------#
# Specific classes, which subclass the base one
#------------------------------------------------------------------------------#
@docstring_fix
class XYAxes(BaseAxes):
    """
    Subclass for ordinary Cartesian-grid axes.
    """
    # Initialize
    name = 'xy'
    def __init__(self, *args, **kwargs):
        # Create simple x by y subplot.
        super().__init__(*args, **kwargs)

    def __getattribute__(self, attr, *args):
        # Attribute
        obj = super().__getattribute__(attr, *args)
        if attr in _center_methods:
            obj = _check_centers(obj)
        elif attr in _edge_methods:
            obj = _check_edges(obj)
        return obj

    def _rcupdate(self):
        # Update the rcParams according to user input.
        # Simply updates the spines and whatnot
        for spine in self.spines.values():
            spine.update(dict(linewidth=rc['axes.linewidth'], color=rc['axes.edgecolor']))
        # Axis settings
        for xy,axis in zip('xy', (self.xaxis, self.yaxis)):
            # Axis label
            axis.label.update(dict(color=rc['axes.edgecolor'],
                fontsize=rc['axes.labelsize'],
                weight=rc['axes.labelweight']))
            # Tick labels
            for t in axis.get_ticklabels():
                t.update(dict(color=rc['axes.edgecolor'], fontsize=rc[xy+'tick.labelsize']))
            # Tick marks
            # NOTE: We decide that tick location should be controlled only
            # by format(), so don't override that here.
            major, minor = rc[xy+'tick.major'], rc[xy+'tick.minor']
            minor.pop('visible') # don't toggle that yet
            major = {key:value for key,value in major.items() if key not in ('bottom','top','left','right')}
            minor = {key:value for key,value in minor.items() if key not in ('bottom','top','left','right')}
            # Apply the settings
            major.update({'color':rc['axes.edgecolor']})
            minor.update({'color':rc['axes.edgecolor']})
            axis.set_tick_params(which='major', **major)
            axis.set_tick_params(which='minor', **minor)
            # Manually update gridlines
            for name,ticks in zip(('grid','gridminor'),(axis.get_major_ticks(), axis.get_minor_ticks())):
                for tick in ticks:
                    tick.gridline.update(rc[name])
            # if grid is not None:
            #     axis.grid(grid, which='major', **rc['grid'])
            # if gridminor is not None:
            #     axis.grid(gridminor, which='minor', **rc['gridminor']) # ignore if no minor ticks

        # Update background patch, with optional hatching
        # Color setup, optional hatching in background of axes
        # You should control transparency by passing transparent=True or False
        # to the savefig command
        self.patch.set_clip_on(False)
        self.patch.set_zorder(-1)
        self.patch.update({'facecolor':rc['axes.facecolor']})
        hatch = rc['axes.facehatch']
        if hatch: # non-empty string or not none
            self.fill_between([0,1], 0, 1, hatch=hatch, zorder=0, # put in back
                facecolor='none', edgecolor='k', transform=self.transAxes)

        # Call parent
        super()._rcupdate()

    # Cool overrides
    def format(self,
        xgrid=None,      ygrid=None,      # gridline toggle
        xdates=False,    ydates=False,    # whether to format axis labels as long datetime strings; the formatter should be a date %-style string
        xspineloc=None,  yspineloc=None,  # deals with spine options
        tickminor=None, xtickminor=True, ytickminor=True, # minor ticks on/off
        gridminor=None, xgridminor=None, ygridminor=None, # minor grids on/off (if ticks off, grid will always be off)
        xtickloc=None,   ytickloc=None,   # which spines to draw ticks on
        xtickdir=None,   ytickdir=None,   # which direction ('in', 'our', or 'inout')
        xticklabeldir=None, yticklabeldir=None, # which direction to draw labels
        xtickrange=None,    ytickrange=None,    # limit regions where we assign ticklabels to major-ticks
        xreverse=False, yreverse=False, # special properties
        xlabel=None,    ylabel=None,    # axis labels
        xlim=None,      ylim=None,
        xscale=None,    yscale=None,
        xlocator=None,  xminorlocator=None, ylocator=None, yminorlocator=None, # locators, or derivatives that are passed to locators
        xscale_kw={}, yscale_kw={},
        xlocator_kw={}, ylocator_kw={},
        xformatter_kw={}, yformatter_kw={},
        xminorlocator_kw={}, yminorlocator_kw={},
        xformatter=None, yformatter=None,
        **kwargs): # formatter
        """
        Format the x/y labels, tick locators, tick formatters, and more.
        Needs more documentation.
        """
        # Pass stuff to parent formatter, e.g. title and abc labeling
        super().format(**kwargs)
        # Set axis scaling and limits
        if xscale is not None:
            if hasattr(xscale,'name'):
                xscale = xscale.name
            self.set_xscale(Scale(xscale, **xscale_kw))
        if yscale is not None:
            if hasattr(yscale,'name'):
                yscale = yscale.name
            self.set_yscale(Scale(yscale, **yscale_kw))
        if xlim is not None:
            if xreverse:
                xlim = xlim[::-1]
            self.set_xlim(xlim)
        if ylim is not None:
            if yreverse:
                ylim = ylim[::-1]
            self.set_ylim(ylim)

        # Control axis ticks and labels and stuff
        xtickminor = tickminor or xtickminor
        ytickminor = tickminor or ytickminor
        xgridminor = gridminor or xgridminor
        ygridminor = gridminor or ygridminor
        for xy, axis, label, tickloc, spineloc, gridminor, tickminor, tickminorlocator, \
                grid, ticklocator, tickformatter, tickrange, tickdir, ticklabeldir, \
                formatter_kw, locator_kw, minorlocator_kw in \
            zip('xy', (self.xaxis, self.yaxis), (xlabel, ylabel), \
                (xtickloc,ytickloc), (xspineloc, yspineloc), # other stuff
                (xgridminor, ygridminor), (xtickminor, ytickminor), (xminorlocator, yminorlocator), # minor ticks
                (xgrid, ygrid),
                (xlocator, ylocator), (xformatter, yformatter), # major ticks
                (xtickrange, ytickrange), # range in which we label major ticks
                (xtickdir, ytickdir), (xticklabeldir, yticklabeldir), # tick direction
                (xformatter_kw, yformatter_kw), (xlocator_kw, ylocator_kw), (xminorlocator_kw, yminorlocator_kw),
                ):
            # Axis spine visibility and location
            sides = ('bottom','top') if xy=='x' else ('left','right')
            for spine, side in zip((self.spines[s] for s in sides), sides):
                # Line properties
                spineloc = getattr(self, xy+'spine_override', spineloc) # optionally override; necessary for twinx/twiny situation
                # Eliminate sides
                if spineloc=='neither':
                    spine.set_visible(False)
                elif spineloc=='both':
                    spine.set_visible(True)
                elif spineloc in sides: # make relevant spine visible
                    b = True if side==spineloc else False
                    spine.set_visible(b)
                elif spineloc is not None:
                    # Special spine location
                    # Note special 'spine location' options include 'zero', 'center',
                    # and tuple with (units, location) where units can be axes, data, or outward
                    if side==sides[0]: # move the left/semabottom spine onto the specified location, with set_position
                        spine.set_visible(True)
                        spine.set_position(spineloc)
                    else:
                        spine.set_visible(False)
            spines = [spine for spine in sides if self.spines[side].get_visible()]

            # Axis label properties
            # First redirect user request to the correct *shared* axes, then
            # redirect to the correct *spanning* axes if the label is meant
            # to span multiple subplot
            if label is not None:
                span = getattr(self, '_span' + xy) # spanning labels toggled?
                share = getattr(self, '_share' + xy)
                # Shared axes
                if share:
                    axis_label = getattr(share, xy + 'axis')
                else:
                    axis_label = axis
                # if span: # seek the edges on the same row/column (will think in terms of an xlabel)
                #     # Function for getting the 'edge' we want to share (bottom row, or leftmost column)
                #     # TODO: Possible duplication? Didn't we rename the axes
                #     # label on 'shared axes' to actually point to their parent
                #     # axes, or did we not do this?
                #     axs = []
                #     edge = lambda ax: getattr(ax, 'rows')[1] if xy=='x' else getattr(ax, 'cols')[0]
                #     panel = lambda ax: (ax.bottompanel or ax) if xy=='x' else (ax.leftpanel or ax)
                #     span = lambda ax: getattr(ax, 'cols') if xy=='x' else getattr(ax, 'rows')
                #     edge_self = edge(self)
                #     for ax in self.figure.axes:
                #         if edge_self==edge(ax):
                #             axs += [panel(ax)]
                #     # Obtain the axes boundaries
                #     range = [value for ax in axs for value in span(ax)]
                #     range = [min(range), max(range)] # the gridspec range
                axis_label.label.set_text(label)

            # Tick properties
            # * Weird issue seems to cause set_tick_params to reset/forget that the grid
            #   is turned on if you access tick.gridOn directly, instead of passing through tick_params.
            #   Since gridOn is undocumented feature, don't use it. So calling _format_axes() a second time will remove the lines
            # * Can specify whether the left/right/bottom/top spines get ticks; sides will be 
            #   group of left/right or top/bottom
            # * Includes option to draw spines but not draw ticks on that spine, e.g.
            #   on the left/right edges
            # First determine tick sides
            ticklocs = sides if tickloc=='both' else () if tickloc in ('neither','none') else None if tickloc is None else (tickloc,)
            if ticklocs is None:
                ticks_sides = {side: False for side in sides if side not in spines}
            else:
                ticks_sides = {side: side in spines and side in ticklocs for side in sides}
            ticks_sides = dict(ticks_sides, **{'label'+side:b for side,b in ticks_sides.items()})
            # Next basic settings
            ticks_major, ticks_minor = {}, {}
            if tickdir is not None:
                ticks_major.update({'direction':tickdir})
                ticks_minor.update({'direction':tickdir})
            if tickdir=='in':
                ticks_major.update({'pad':1}) # ticklabels should be much closer
                ticks_minor.update({'pad':1})
            if ticklabeldir=='in': # put tick labels inside the plot; sometimes might actually want this
                pad = rc['majorlen'] + rc['tickpad'] + rc['small']
                ticks_major.update({'pad':-pad})
                ticks_minor.update({'pad':-pad})
            # Finally, apply
            axis.set_tick_params(which='major', **ticks_sides, **ticks_major)
            axis.set_tick_params(which='minor', **ticks_sides, **ticks_minor) # have length

            # Set the major and minor locators and formatters
            # Also automatically detect whether axis is a 'time axis' (i.e.
            # whether user has plotted something with x/y as datetime/date/np.datetime64
            # objects, and matplotlib automatically set the unit converter)
            time = isinstance(axis.converter, mdates.DateConverter)
            if ticklocator is not None:
                axis.set_major_locator(Locator(ticklocator, time=time, **locator_kw))
            if tickformatter is not None:
                axis.set_major_formatter(Formatter(tickformatter, tickrange=tickrange, time=time, **formatter_kw))
            if not tickminor and tickminorlocator is None:
                axis.set_minor_locator(Locator('null'))
            elif tickminorlocator is not None:
                axis.set_minor_locator(Locator(tickminorlocator, minor=True, time=time, **minorlocator_kw))
            axis.set_minor_formatter(mticker.NullFormatter())
            # Update text, and ensure that we don't have tick labels where
            # there are no ticks!
            for t in axis.get_ticklabels():
                if not ticklocs and ticklocs is not None:
                    t.set_visible(False)
            if ticklocs:
                labelpos = [tickloc for tickloc in ticklocs if self.spines[tickloc].get_visible()]
                if len(labelpos)==1:
                    axis.set_label_position(labelpos[0])

            # Gridline activation and setting (necessary because rcParams has no 'minorgrid'
            # property, must be set in rcPubPlot)
            # NOTE: Inexplicably, for a twinx axis, could only get the minor gridlines
            # to disappear if we changed the 'visible' property on each one.
            # for tick in axis.get_major_ticks():
            #     if grid is not None:
            #         tick.gridline.set_visible(grid)
            #     tick.gridline.update(rc['grid']) # already set but why not, for symmetry
            # # for tick in axis.minorTicks:
            # for tick in axis.get_minor_ticks():
            #     if gridminor is not None:
            #         tick.gridline.set_visible(gridminor)
            #     tick.gridline.update(rc['gridminor'])
            # For some insane reasion, these are ***both*** needed
            # Without this below stuff, e.g. gridminor=True doesn't draw gridlines
            if grid is not None: # grid changes must be after tick
                axis.grid(grid, which='major', **rc['grid'])
            if gridminor is not None:
                axis.grid(gridminor, which='minor', **rc['gridminor']) # ignore if no minor ticks

    def twiny(self, **kwargs):
        # Create second x-axis extending from shared ("twin") y-axis
        # Note: Cannot wrap twiny() because then the axes created will be
        # instantiated from the parent class, which doesn't have format() method.
        # Instead, use hidden method _make_twin_axes.
        # See https://github.com/matplotlib/matplotlib/blob/master/lib/matplotlib/axes/_subplots.py
        ax = self._make_twin_axes(sharey=self, projection=self.name)
        self.xaxis.tick_bottom()
        ax.xaxis.tick_top()
        ax.xaxis.set_label_position('top')
        ax.set_autoscaley_on(self.get_autoscaley_on())
        ax.yaxis.set_visible(False)
        ax.patch.set_visible(False)
        ax.grid(False)
        # Special settings, force spine locations when format() called
        self.xspine_override = 'bottom' # original axis ticks on bottom
        ax.xspine_override   = 'top' # new axis ticks on top
        ax.yspine_override   = 'neither'
        return ax

    def twinx(self, **kwargs):
        # Create second y-axis extending from shared ("twin") x-axis
        # Note: Cannot wrap twinx() because then the axes created will be
        # instantiated from the parent class, which doesn't have format() method.
        # Instead, use hidden method _make_twin_axes.
        ax = self._make_twin_axes(sharex=self, projection=self.name)
        self.yaxis.tick_left()
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position('right')
        ax.yaxis.set_offset_position('right')
        ax.set_autoscalex_on(self.get_autoscalex_on())
        ax.xaxis.set_visible(False)
        ax.patch.set_visible(False)
        ax.grid(False)
        # Special settings, force spine locations when format() called
        self.yspine_override = 'left' # original axis ticks on left
        ax.yspine_override   = 'right' # new axis ticks on right
        ax.xspine_override   = 'neither'
        return ax

    # def make_inset_locator(self, bounds, trans):
    #     # Helper function, had to be copied from private matplotlib version.
    #     def inset_locator(ax, renderer):
    #         bbox = mtransforms.Bbox.from_bounds(*bounds)
    #         bb = mtransforms.TransformedBbox(bbox, trans)
    #         tr = self.figure.transFigure.inverted()
    #         bb = mtransforms.TransformedBbox(bb, tr)
    #         return bb
    #     return inset_locator
    #
    # def inset_axes(self, bounds, *, transform=None, zorder=5,
    #         **kwargs):
    #     # Create inset of same type.
    #     # Defaults
    #     if transform is None:
    #         transform = self.transAxes
    #     label = kwargs.pop('label', 'inset_axes')
    #     # This puts the rectangle into figure-relative coordinates.
    #     locator = self.make_inset_locator(bounds, transform)
    #     bb = locator(None, None)
    #     ax = XYAxes(self.figure, bb.bounds, zorder=zorder, label=label, **kwargs)
    #     # The following locator lets the axes move if in data coordinates, gets called in ax.apply_aspect()
    #     ax.set_axes_locator(locator)
    #     self.add_child_axes(ax)
    #     return ax
    #
    # def inset(self, *args, **kwargs):
    #     # Inset
    #     return self.inset_axes(*args, **kwargs)


@docstring_fix
class PanelAxes(XYAxes):
    """
    Axes with added utilities that make it suitable for holding a legend or
    colorbar meant to reference several other subplots at once.

    Todo
    ----
    Updated rcparam stuff; better to simply be inefficient and, when necessary,
    delete an Axes with ax.clear() then update it after setting rcparams, or use
    or ax.remove() followed by ax.update_from() and/or ax.redraw_idle()

    Notes
    -----
    See: https://stackoverflow.com/a/52121237/4970632
    Also an example: https://stackoverflow.com/q/26236380/4970632
    """
    name = 'panel'
    def __init__(self, *args, panelside=None, invisible=False, **kwargs):
        # Initiate
        if panelside is None:
            raise ValueError('Must specify side.')
        super().__init__(*args, panelside=panelside, **kwargs)
        # Make everything invisible
        if invisible:
            self.invisible()

    def invisible(self):
        # Make axes invisible
        for s in self.spines.values():
            s.set_visible(False)
        self.xaxis.set_visible(False)
        self.yaxis.set_visible(False)
        self.patch.set_alpha(0)

    def legend(self, handles, **kwargs):
        # Allocate invisible axes for drawing legend.
        # Returns the axes and the output of legend_factory().
        self.invisible()
        kwlegend = {'borderaxespad':  0,
                    'frameon':        False,
                    'loc':            'upper center',
                    'bbox_transform': self.transAxes}
        kwlegend.update(kwargs)
        return self, legend_factory(self, handles, **kwlegend)

    def colorbar(self, *args, i=0, n=1, length=1, **kwargs):
        # Draw colorbar with arbitrary length relative to full length of the
        # panel, and optionally *stacking* multiple colorbars
        # Will always redraw an axes with new subspec
        self.invisible()
        figure = self.figure
        side = self.panelside
        subspec = self.get_subplotspec()
        if n>2:
            raise ValueError('I strongly advise against drawing more than 2 stacked colorbars.')
        if length!=1 or n!=1:
            # First get gridspec
            if side in ['bottom','top']:
                gridspec = FlexibleGridSpecFromSubplotSpec(
                        nrows=n,  ncols=3,
                        wspace=0, hspace=0,
                        subplot_spec=subspec,
                        width_ratios=((1-length)/2, length, (1-length)/2)
                        )
                subspec = gridspec[i,1]
            elif side in ['left','right']:
                gridspec = FlexibleGridSpecFromSubplotSpec(
                        nrows=3,  ncols=n,
                        hspace=0, wspace=0,
                        subplot_spec=subspec,
                        height_ratios=((1-length)/2, length, (1-length)/2)
                        )
                subspec = gridspec[1,i]
            # Next redraw axes
            # self.remove() # save memory
            self.set_visible(False)
        # Allocate axes for drawing colorbar.
        # Returns the axes and the output of colorbar_factory().
        ax = figure.add_subplot(subspec, projection=None)
        if side in ['bottom','top']:
            outside, inside = 'bottom', 'top'
            if side=='top':
                outside, inside = inside, outside
            ticklocation = outside if i==n-1 else inside
            orientation  = 'horizontal'
        elif side in ['left','right']:
            outside, inside = 'left', 'right'
            if side=='right':
                outside, inside = inside, outside
            ticklocation = outside if i==n-1 else inside
            orientation  = 'vertical'
        kwargs.update({'orientation':orientation, 'ticklocation':ticklocation})
        return ax, colorbar_factory(ax, *args, **kwargs)

class MapAxes(BaseAxes):
    """
    Dummy intermediate class that just disables a bunch of methods that are
    inappropriate for map projections.
    """
    # Disable some methods to prevent weird shit from happening
    # Originally used property decorators for this but way too verbose
    # See: https://stackoverflow.com/a/23126260/4970632
    def __getattribute__(self, attr, *args):
        if attr in _map_disabled_methods:
            raise NotImplementedError('Invalid plotting function {} for map projection axes.'.format(attr))
        return super().__getattribute__(attr, *args)

@docstring_fix
class BasemapAxes(MapAxes):
    """
    Axes subclass for basemap plotting.
    """
    name = 'basemap'
    pseudocyl = ['moll','robin','eck4','kav7','sinu','mbtfpq','vandg','hammer']
    def __init__(self, *args, map_projection=None, **kwargs):
        """
        Declare basemap projection instance, add it as the 'm' attribute.
        The 'map_projection' argument sets projection, because this axes itself
        is called from add_subplot using projection='basemap'.
        """
        import mpl_toolkits.basemap as mbasemap # verify package is available
        # * Must set boundary before-hand, otherwise the set_axes_limits method called
        #   by mcontourf/mpcolormesh/etc draws two mapboundary Patch objects called "limb1" and
        #   "limb2" automatically: one for fill and the other for the edges
        # * Then, since the patch object in _mapboundarydrawn is only the fill-version, calling
        #   drawmapboundary() again will replace only *that one*, but the original visible edges
        #   are still drawn -- so e.g. you can't change the color
        # * If you instead call drawmapboundary right away, _mapboundarydrawn will contain
        #   both the edges and the fill; so calling it again will replace *both*
        if not isinstance(map_projection, mbasemap.Basemap):
            raise ValueError('You must initialize BasemapAxes with map_projection=(basemap.Basemap instance).')
        super().__init__(*args, **kwargs)
        self.m = map_projection
        self.boundary = None
        self.axesPatch = self.patch # for bugfix
        self._recurred = False # use this so we can override plotting methods
        if map_projection.projection in self.pseudocyl: # otherwise the spines are map boundary
            self.boundary = self.m.drawmapboundary(ax=self)

    # Basemap overrides
    # WARNING: Never ever try to just make blanket methods on the Basemap
    # instance accessible from axes instance! Can of worms and had bunch of
    # weird errors! Just pick the ones you think user will want to use.
    def __getattribute__(self, attr, *args):
        if attr=='pcolorpoly': # need to specify this again to access the .m method
            attr = 'pcolor' # use alias so don't run into recursion issues due to internal pcolormesh calls to pcolor()
        obj = super().__getattribute__(attr, *args)
        if attr in _line_methods or attr in _edge_methods or attr in _center_methods:
            obj = _m_call(self, obj) # this must be the *last* step!
            if attr in _line_methods:
                obj = _cycle_features(self, obj)
                obj = _linefix_basemap(self, obj)
            elif attr in _edge_methods or attr in _center_methods:
                obj = _cmap_features(self, obj)
                obj = _gridfix_basemap(self, obj)
                if attr in _edge_methods:
                    obj = _check_edges(obj)
                else:
                    obj = _check_centers(obj)
            obj = _no_recurse(self, obj)
        return obj

    # Format basemap axes
    # Add documentation here.
    def format(self, color=None,
        oceans=False, coastlines=False, land=False, # coastlines and land
        latlabels=[0,0,0,0], lonlabels=[0,0,0,0], # sides for labels [left, right, bottom, top]
        latlocator=None, latminorlocator=None,
        lonlocator=None, lonminorlocator=None,
        **kwargs):
        # Pass stuff to parent formatter, e.g. title and abc labeling
        super().format(**kwargs)

        # Basemap axes setup
        # Coastlines, parallels, meridians
        if coastlines:
            props = rc['coastlines']
            p = self.m.drawcoastlines(**props, ax=self)
        if land:
            props = rc['land']
            p = self.m.fillcontinents(ax=self)
            for _ in p:
                _.update(props)

        # Longitude/latitude lines
        # Make sure to turn off clipping by invisible axes boundary; otherwise
        # get these weird flat edges where map boundaries, parallel/meridian markers come up to the axes bbox
        tsettings = {'color':rc['xtick.color'], 'fontsize':rc['xtick.labelsize']}
        if latlocator is not None:
            if utils.isnumber(latlocator):
                latlocator = utils.arange(self.m.latmin+latlocator, self.m.latmax-latlocator, latlocator)
            p = self.drawparallels(latlocator, labels=latlabels, ax=self)
            for pi in p.values(): # returns dict, where each one is tuple
                for _ in [i for j in pi for i in j]: # magic
                    if isinstance(_, mtext.Text):
                        _.update(tsettings)
                    else:
                        _.set_clip_on(True) # no gridlines past boundary
                        _.update(rc['lonlatlines'])
                        # _.set_linestyle(linestyle)
                # tried passing clip_on to the above, but it does nothing; must set
                # for lines created after the fact
        if lonlocator is not None:
            latlabels[2:] = latlabels[2:][::-1] # default is left/right/top/bottom which is dumb
            lonlabels[2:] = lonlabels[2:][::-1] # change to left/right/bottom/top
            if utils.isnumber(lonlocator):
                lonlocator = utils.arange(self.m.lonmin+lonlocator, self.m.lonmax-lonlocator, lonlocator)
            p = self.m.drawmeridians(lonlocator, labels=lonlabels, ax=self)
            for pi in p.values():
                for _ in [i for j in pi for i in j]: # magic
                    if isinstance(_, mtext.Text):
                        _.update(tsettings)
                    else:
                        _.set_clip_on(True) # no gridlines past boundary
                        _.update(rc['lonlatlines'])
                        # _.set_linestyle(linestyle)

        # Map boundary
        # * First have to *manually replace* the old boundary by just deleting
        #   the original one; note this requires drawmapboundary() was called
        #   when the basemap was first instantiated; see notes in subplots() command.
        # * If boundary is drawn successfully should be able to call
        #   self.m._mapboundarydrawn.set_visible(False) and edges/fill color disappear
        # * For now will enforce that map plots *always* have background whereas
        #   axes plots can have transparent background
        if self.m._mapboundarydrawn:
            self.m._mapboundarydrawn.remove()
        outline = {'linewidth': rc['axes.linewidth'],
                   'color':     rc['axes.edgecolor']}
        if self.m.projection in self.pseudocyl:
            self.patch.set_alpha(0) # make patch invisible
            p = self.m.drawmapboundary(fill_color=color, ax=self, **outline) # set fill_color to 'none' to make transparent
            p.set_rasterized(False) # not sure about this; might be rasterized
            p.set_clip_on(False) # so edges of LINE denoting boundary aren't cut off
        else: # use the settings to apply to Axes patch; the basemap API fails here
            self.patch.set_facecolor(color)
            self.patch.set_edgecolor('none')
            for spine in self.spines.values():
                spine.update(outline)

@docstring_fix
# class CartopyAxes(GeoAxes, MapAxes):
class CartopyAxes(MapAxes, GeoAxes): # custom one has to be higher priority, so the methods can overwrite stuff
    # Cartopy takes advantage of documented feature where any class with method
    # named _as_mpl_axes can be passed as 'projection' object.
    # Feature documented here: https://matplotlib.org/devel/add_new_projection.html
    # Used in Projection parent class here: https://scitools.org.uk/cartopy/docs/v0.13/_modules/cartopy/crs
    name = 'cartopy'
    def __init__(self, *args, map_projection=None, circle_center=90, circle_edge=0, **kwargs):
        """
        Initialize cartopy projection, and allow for *partial* (i.e. not global)
        coverage for azimuthal projections by zooming into the full projection,
        then drawing a circle boundary around some latitude away from the center.
        * The 'map_projection' argument sets projection, because this axes itself
          is called from add_subplot using projection='basemap'.
        * Number 'ncircle' controls number of points for drawing circular projection
          boundary. For more info see: https://scitools.org.uk/cartopy/docs/v0.15/examples/always_circular_stereo.html
        """
        # Dependencies
        import cartopy.crs as ccrs # verify package is available

        # Do the GeoAxes initialization steps manually (there are very few)
        if not isinstance(map_projection, ccrs.Projection):
            raise ValueError('You must initialize CartopyAxes with map_projection=(cartopy.crs.Projection instance).')
        self._hold = None # dunno
        self.projection = map_projection # attribute used extensively by GeoAxes methods, and by builtin one

        # Below will call BaseAxes, which will call GeoAxes as the superclass
        # NOTE: Previously did stuff in __init__ manually, and called self._boundary,
        # which hides existing border patch and rewrites as None. Don't do that again.
        super().__init__(*args, map_projection=map_projection, **kwargs)

        # Apply circle boundary
        self._land = None
        self._ocean = None
        self._coastlines = None
        crs_circles = (ccrs.LambertAzimuthalEqualArea, ccrs.AzimuthalEquidistant)
        if any(isinstance(map_projection, cp) for cp in crs_circles):
            # self.projection.threshold = kwargs.pop('threshold', self.projection.threshold) # optionally modify threshold
            self.set_extent([-180, 180, circle_edge, circle_center], PlateCarree) # use platecarree transform
            self.set_boundary(circle(100), transform=self.transAxes)

    def _as_mpl_axes(self):
        # Don't think this is ever used.
        return GeoAxes, {'map_projection': self}

    def __getattribute__(self, attr, *args):
        obj = super().__getattribute__(attr, *args)
        if attr in _line_methods:
            obj = _linefix_cartopy(obj)
        elif attr in _edge_methods or attr in _center_methods:
            obj = _gridfix_cartopy(obj)
            if attr in _edge_methods:
                obj = _check_edges(obj)
            else:
                obj = _check_centers(obj)
        return obj

    def _rcupdate(self):
        # Update properties controlled by custom rc settings
        self.set_global() # see: https://stackoverflow.com/a/48956844/4970632
        self.background_patch.update({'facecolor': rc['axes.facecolor']})
        self.outline_patch.update({'edgecolor': rc['axes.edgecolor'],
                                   'linewidth': rc['axes.linewidth']})
        # Call parent
        super()._rcupdate()

    # Format cartopy GeoAxes.
    # Add documentation here.
    def format(self,
        xlim=None, ylim=None,
        oceans=False, land=False, coastlines=False, # coastlines and continents
        latlabels=[0,0,0,0], lonlabels=[0,0,0,0], # sides for labels [left, right, bottom, top]
        latlocator=None, latminorlocator=None, lonlocator=None, lonminorlocator=None,
        **kwargs):
        # Dependencies
        import cartopy.feature as cfeature
        import cartopy.crs as ccrs # verify package is available
        from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER

        # Pass stuff to parent formatter, e.g. title and abc labeling
        super().format(**kwargs)

        # Configure extents?
        # WARNING: The set extents method tries to set a *rectangle* between
        # the *4* (x,y) coordinate pairs (each corner), so something like
        # (-180,180,-90,90) will result in *vertical line*, causing error!
        # NOTE: proj4_params stores keyword-arg pairs, proj4_init stores
        # the shell string passed
        # NOTE: They may add this in set_xlim and set_ylim in the
        # near future; see:
        # https://github.com/SciTools/cartopy/blob/master/lib/cartopy/mpl/geoaxes.py#L638
        if xlim is not None or ylim is not None:
            xlim = xlim or [None,None]
            ylim = ylim or [None,None]
            xlim, ylim = [*xlim], [*ylim]
            lon_0 = self.projection.proj4_params.get('lon_0', 0)
            if xlim[0] is None:
                xlim[0] = lon_0 - 180
            if xlim[1] is None:
                xlim[1] = lon_0 + 180
            if ylim[0] is None:
                ylim[0] = -90
            if ylim[1] is None:
                ylim[1] = 90
            self.set_extent([*xlim, *ylim], PlateCarree)

        # Draw gridlines
        # WARNING: For some reason very weird side effects happen if you try
        # to call gridlines() twice on same axes. Can't do it. Which is why
        # we do this nonsense with the formatter below, instead of drawing 'major'
        # grid lines and 'minor' grid lines.
        lonvec = lambda v: [] if v is None else [*v] if utils.isvector(v) else [*utils.arange(-180,180,v)]
        latvec = lambda v: [] if v is None else [*v] if utils.isvector(v) else [*utils.arange(-90,90,v)]
        lonminorlocator, latminorlocator = lonvec(lonminorlocator), latvec(latminorlocator)
        lonlocator, latlocator = lonvec(lonlocator), latvec(latlocator)
        lonlines = lonminorlocator or lonlocator # where we draw gridlines
        latlines = latminorlocator or latlocator

        # First take care of gridlines
        draw_labels = (isinstance(self.projection,ccrs.Mercator) or isinstance(self.projection,ccrs.PlateCarree))
        if latlines and latlines[0]==-90:
            latlines[0] += 0.001
        if lonlines and lonlines[0]==-90:
            lonlines[0] -= 0.001
        gl = self.gridlines(**rc['lonlatlines'], draw_labels=draw_labels)
        gl.xlocator = mticker.FixedLocator(lonlines)
        gl.ylocator = mticker.FixedLocator(latlines)

        # Now take care of labels
        if draw_labels:
            lonfunc = lambda x,y: LONGITUDE_FORMATTER(x) if x in lonlocator else ''
            latfunc = lambda x,y: LATITUDE_FORMATTER(x) if x in latlocator else ''
            gl.xformatter = mticker.FuncFormatter(lonfunc)
            gl.yformatter = mticker.FuncFormatter(latfunc)
            gl.xlabels_bottom, gl.xlabels_top = latlabels[2:]
            gl.ylabels_left, gl.ylabels_right = lonlabels[:2]

        # Add geographic features
        # Use the NaturalEarthFeature to get more configurable resolution; can choose
        # between 10m, 50m, and 110m (scales 1:10mil, 1:50mil, and 1:110mil)
        if coastlines and not self._coastlines:
            # self.add_feature(cfeature.COASTLINE, **rc['coastlines'])
            print('Add coastlines.')
            feat = cfeature.NaturalEarthFeature('physical', 'coastline', '50m')
            self.add_feature(feat, **rc['coastlines'])
            self._coastlines = feat
        if land and not self._land:
            # self.add_feature(cfeature.LAND, **rc['continents'])
            print('Add land.')
            feat = cfeature.NaturalEarthFeature('physical', 'land', '50m')
            self.add_feature(feat, **rc['land'])
            self._land = feat
        if oceans and not self._ocean:
            # self.add_feature(cfeature.OCEAN, **rc['oceans'])
            print('Add oceans.')
            feat = cfeature.NaturalEarthFeature('physical', 'ocean', '50m')
            self.add_feature(feat, **rc['oceans'])
            self._ocean = feat


@docstring_fix
class PolarAxes(MapAxes, PolarAxes):
    """
    Thin decorator around PolarAxes with my new plotting features.
    So far just intended to mix the two classes.
    """
    name = 'newpolar'

# Register the projection
register_projection(XYAxes)
register_projection(PanelAxes)
register_projection(PolarAxes)
register_projection(BasemapAxes)
register_projection(CartopyAxes)

#------------------------------------------------------------------------------#
# Custom legend and colorbar factories
#------------------------------------------------------------------------------#
def map_projection_factory(package, projection, **kwargs):
    """
    Returns Basemap object or cartopy ccrs instance.
    """
    # Initial stuff
    # Create projection and determine required aspect ratio
    if package=='basemap':
        import mpl_toolkits.basemap as mbasemap # verify package is available
        projection = mbasemap.Basemap(projection=(projection or 'cyl'), **{**kwargs, 'fix_aspect':True}) # cylindrical by default
        aspect = (projection.urcrnrx - projection.llcrnrx)/(projection.urcrnry - projection.llcrnry)
    # Get the projection instance from a string and determine required aspect ratio
    elif package=='cartopy':
        import cartopy.crs as ccrs # verify package is importable
        crs_translate = { # less verbose keywords, actually match proj4 keywords and are similar to basemap
            **{k:'central_latitude'  for k in ['lat0','lat_0']},
            **{k:'central_longitude' for k in ['lon0', 'lon_0']},
            }
        crs_dict = { # interpret string, create cartopy projection
            **{key: ccrs.PlateCarree   for key in ['cyl','rectilinear','pcarree','platecarree']},
            **{key: ccrs.Mollweide     for key in ['moll','mollweide']},
            **{key: ccrs.Stereographic for key in ['stereo','stereographic']},
            'aeqd': ccrs.AzimuthalEquidistant, 'aeqa': ccrs.LambertAzimuthalEqualArea,
            'mercator': ccrs.Mercator, 'robinson': ccrs.Robinson, 'ortho': ccrs.Orthographic,
            'hammer': Hammer,       'aitoff': Aitoff,
            'wintri': WinkelTripel, 'kav7':   KavrayskiyVII,
            }
        projection = projection or 'cyl'
        if projection not in crs_dict:
            raise ValueError(f'For cartopy, projection must be one of the following: {", ".join(crs_dict.keys())}.')
        projection = crs_dict[projection](**{crs_translate.get(key,key):value for key,value in kwargs.items()})
        aspect = (np.diff(projection.x_limits)/np.diff(projection.y_limits))[0]
    # Error
    else:
        raise ValueError(f'Unknown package "{package}".')
    return projection, aspect

def legend_factory(ax, handles=None, align=None, rowmajor=True, **lsettings): #, settings=None): # can be updated
    """
    Function for formatting legend-axes (invisible axes with centered legends on them).
    Should update my legend function to CLIP the legend box when it goes outside axes area, so
    the legend-width and bottom/right widths can be chosen propertly/separately.
    """
    # First get legend settings (usually just one per plot so don't need to declare
    # this dynamically/globally), and interpret kwargs
    if 'ncols' in lsettings:
        lsettings['ncol'] = lsettings.pop('ncols') # pyplot subplot uses 'ncols', but legend uses 'ncol'... annoying!
    if 'frame' in lsettings: # again, confusing choice
        lsettings['frameon'] = lsettings.pop('frame')
    # Setup legend text and handle properties
    hsettings = {}
    for candidate in ['linewidth', 'color']: # candidates for modifying legend objects
        if candidate in lsettings:
            hsettings[candidate] = lsettings.pop(candidate)
    hsettings.update({'alpha':1.0}) # always maximimum opacity

    # Detect if user wants to specify rows manually
    # Gives huge latitude for user input:
    #   1) user can specify nothing and align will be inferred (list of iterables
    #      will always be False, i.e. we draw consecutive legends, and list of handles is always true)
    #   2) user can specify align (needs list of handles for True, list of handles or list
    #      of iterables for False and if the former, will turn into list of iterables)
    if handles is None:
        handles = ax.get_legend_handles_labels()[0]
    for i,handle in enumerate(handles):
        if hasattr(handle, 'cmap'):
            # Make sure we sample the *center* of the colormap
            print('Warning: Creating legend for colormap object.')
            size = np.mean(handle.get_sizes())
            handles[i] = ax.scatter([0], [0],
                                 markersize=size,
                                 color=[handle.cmap(0.5)],
                                 label=handle.get_label())
    list_of_lists = not isinstance(handles[0], martist.Artist)
    if align is None: # automatically guess
        align = not list_of_lists
    else: # standardize format based on input
        if not align and not list_of_lists: # separate into columns
            # raise ValueError("Need to specify number of columns with ncol.")
            list_of_lists = True
            lsettings['ncol'] = lsettings.get('ncol',3)
            handles = [handles[i*lsettings['ncol']:(i+1)*lsettings['ncol']]
                        for i in range(len(handles))] # to list of iterables
        if align and list_of_lists: # unfurl, because we just want one legend!
            list_of_lists = False
            handles = [handle for isiterable in handles for handle in isiterable]
            list_of_lists = False # no longer is list of lists

    # Now draw legend, with two options
    # 1) Normal legend, just draw everything like normal and columns
    # will be aligned; we re-order handles to be row-major, is only difference
    if align:
        # Prepare settings
        if list_of_lists:
            lsettings['ncol'] = len(handles[0]) # choose this for column length
        elif 'ncol' not in lsettings:
            lsettings['ncol'] = 3
        # Split up into rows and columns -- by default matplotlib will
        # sort them in ***column-major*** order but that's dumb, we want row-major!
        # See: https://stackoverflow.com/q/10101141/4970632
        if rowmajor:
            newhandles = []
            ncol = lsettings['ncol'] # number of columns
            handlesplit = [handles[i*ncol:(i+1)*ncol] for i in range(len(handles)//ncol+1)] # split into rows
            nrowsmax, nfinalrow = len(handlesplit), len(handlesplit[-1]) # max possible row count, and columns in final row
            nrows = [nrowsmax]*nfinalrow + [nrowsmax-1]*(lsettings['ncol']-nfinalrow)
                # e.g. if 5 columns, but final row length 3, columns 0-2 have N rows but 3-4 have N-1 rows
            for col,nrow in enumerate(nrows): # iterate through cols
                newhandles.extend(handlesplit[row][col] for row in range(nrow))
            handles = newhandles
        # Finally draw legend, mimicking row-major ordering
        leg = super(BaseAxes, ax).legend(handles=handles, **lsettings)
        legends = [leg]
    # 2) Separate legend for each row
    # The labelspacing/borderspacing will be exactly replicated, as if we were
    # using the original legend command
    # Means we also have to overhaul some settings
    else:
        legends = []
        for override in ['loc','ncol','bbox_to_anchor','borderpad','borderaxespad','frameon','framealpha']:
            lsettings.pop(override, None)
        # Determine space we want sub-legend to occupy, as fraction of height
        # Don't normally save "height" and "width" of axes so keep here
        fontsize = lsettings.get('fontsize', None) or rc['legend.fontsize']
        spacing = lsettings.get('labelspacing', None) or rc['legend.labelspacing']
        interval = 1/len(handles) # split up axes
        interval = (((1 + spacing)*fontsize)/72) / \
                (ax.figure.get_figheight() * np.diff(ax._position.intervaly))
        # Iterate and draw
        if not rowmajor:
            raise ValueError('Using rowmajor=False with align=False does not make sense.')
        for h,hs in enumerate(handles):
            bbox = mtransforms.Bbox([[0,1-(h+1)*interval],[1,1-h*interval]])
            leg = super(BaseAxes, ax).legend(handles=hs, ncol=len(hs),
                loc='center',
                frameon=False,
                borderpad=0,
                bbox_to_anchor=bbox,
                **lsettings) # _format_legend is overriding original legend Method
            legends.append(leg)
        for l in legends[:-1]:
            ax.add_artist(l) # because matplotlib deletes previous ones
    # Properties for legends
    outline = {'linewidth': rc['axes.linewidth'],
               'edgecolor': rc['axes.edgecolor'],
               'facecolor': rc['axes.facecolor']}
    for leg in legends:
        leg.legendPatch.update(outline) # or get_frame()
        for obj in leg.legendHandles:
            obj.update(hsettings)
        # for t in leg.texts:
        #     t.update(tsettings) # or get_texts()
    return legends

def colorbar_factory(ax, mappable, cgrid=False, clocator=None,
        ctickminor=False, cminorlocator=None, cformatter=None, clabel=None,
        errfix=True, extend='neither', extendlength=0.2, # in inches
        values=None, orientation='horizontal', ticklocation='outer', **kwargs): #, settings=None):
    """
    Description
    -----------
    Function for formatting colorbar-axes (axes that are "filled" by a colorbar).
    * There are options on the colorbar object (cb.locator, cb.formatter with cb.update_ticks)
        and by passing kwargs (ticks=x, format=y) that allow uer to not reference the underlying
        "axes" when fixing ticks. Don't use this functionality because not necessary for us and
        is missing many features, e.g. minorlocators/minorformatters. Also is different syntax.
    * There is an INSANELY WEIRD problem with colorbars when simultaneously passing levels
        and norm object to a mappable; fixed by passing vmin/vmax INSTEAD OF levels 
    (see: https://stackoverflow.com/q/40116968/4970632).
    * Problem is, often WANT levels instead of vmin/vmax, while simultaneously
        using a Normalize (for example) to determine colors between the levels
    (see: https://stackoverflow.com/q/42723538/4970632).
    * Workaround is to make sure locators are in vmin/vmax range exclusively;
        cannot match/exceed values.
    * The 'extend' kwarg is used for the case when you are manufacturing colorbar
        from list of colors or lines. Most of the time want 'neither'.
    Todo
    ----
    Issue appears where the normalization vmin/vmax are outside of explicitly declared "levels"
    minima and maxima but that is probaby appropriate. If your levels are all within vmin/vmax,
    you will get discrete jumps outside of range and the extendlength at ends of colorbars will be weird.
    """
    # Make sure to eliminate ticks
    # cax.xaxis.set_tick_params(which='both', bottom=False, top=False)
    # cax.yaxis.set_tick_params(which='both', bottom=False, top=False)
    # Test if we were given a mappable, or iterable of stuff; note Container and
    # PolyCollection matplotlib classes are iterable.
    fromlines, fromcolors = False, False
    if not isinstance(mappable, martist.Artist) and not isinstance(mappable, mcontour.ContourSet):
        if isinstance(mappable[0], martist.Artist):
            fromlines = True # we passed a bunch of line handles; just use their colors
        else:
            fromcolors = True # we passed a bunch of color strings or tuples
    csettings = {'cax':ax, 'orientation':orientation, 'use_gridspec':True, # use space afforded by entire axes
                 'spacing':'uniform', 'extend':extend, 'drawedges':cgrid} # this is default case unless mappable has special props
    # Update with user-kwargs
    csettings.update(**kwargs)
    if hasattr(mappable, 'extend') and mappable.extend is not None:
        csettings.update({'extend':mappable.extend})

    # Option to generate colorbar/colormap from line handles
    # * Note the colors are perfect if we don't extend them by dummy color on either side,
    #   but for some reason labels for edge colors appear offset from everything
    # * Too tired to figure out why so just use this workaround
    # TODO TODO TODO: This should be abstracted away into the colormap
    # retrieval routines in colortools.py
    if fromcolors: # we passed the colors directly
        colors = mappable
        if values is None:
            raise ValueError('Must pass "values", corresponding to list of colors.')
    if fromlines: # the lines
        if values is None:
            raise ValueError('Must pass "values", corresponding to list of handles.')
        if len(mappable)!=len(values):
            raise ValueError('Number of "values" should equal number of handles.')
        colors = [h.get_color() for h in mappable]
    if fromlines or fromcolors:
        # colors = ['#ffffff'] + colors + ['#ffffff']
        values = np.array(values) # needed for below
        # colors = colors[:1] + colors + colors[-1:]
        colormap = mcolors.LinearSegmentedColormap.from_list('tmp', colors, N=len(colors)) # note that
            # the 'N' is critical; default 'N' is otherwise 256, and can get weird artifacts due to
            # unintentionally sampling some 'new' colormap colors; very bad!
        levels = utils.edges(values) # get "edge" values between centers desired
        values = utils.edges(values) # this works empirically; otherwise get weird situation with edge-labels appearing on either side
        mappable = plt.contourf([[0,0],[0,0]], levels=levels, cmap=colormap,
                extend='neither', norm=colortools.BinNorm(values)) # workaround
        if clocator is None: # in this case, easy to assume user wants to label each value
            clocator = values
    if clocator is None:
        clocator = getattr(mappable, 'levels', None)
        if clocator is not None:
            step = 1+len(clocator)//20
            clocator = clocator[::step]

    # Determine major formatters and major/minor tick locators
    # Can pass clocator/cminorlocator as the *jump values* between the mappables
    # vmin/vmax if desired
    normfix = False # whether we need to modify the norm object
    locators = [] # put them here
    for i,locator in enumerate((clocator,cminorlocator)):
        # Get the locator values
        # Need to use tick_values instead of accessing 'locs' attribute because
        # many locators don't have these attributes; require norm.vmin/vmax as input
        if i==1 and not ctickminor and locator is None: # means we never wanted minor ticks
            locators.append(Locator('null'))
            continue
        values = np.array(Locator(locator).tick_values(mappable.norm.vmin, mappable.norm.vmax)) # get the current values
        # Modify ticks to work around mysterious error, and to prevent annoyance
        # where minor ticks extend beyond extendlength.
        # We need to figure out the numbers that will eventually be rendered to
        # solve the error, so we will always use a fixedlocator.
        values_min = np.where(values>=mappable.norm.vmin)[0]
        values_max = np.where(values<=mappable.norm.vmax)[0]
        if len(values_min)==0 or len(values_max)==0:
            raise ValueError(f'No ticks are within the colorbar range {mappable.norm.vmin:.3g} to {mappable.norm.vmax:.3g}.')
        values_min, values_max = values_min[0], values_max[-1]
        values = values[values_min:values_max+1]
        if values[0]==mappable.norm.vmin:
            normfix = True
        if i==1:
            # Prevent annoying major/minor overlaps where one is slightly shifted left/right
            # Consider floating point weirdness too
            eps = 1e-10
            # length = len(values)
            values = [v for v in values if not any(o+eps >= v >= o-eps for o in fixed)]
            # print(f'Removed {length-len(values)}/{length} minor ticks(s).')
        fixed = values # record as new variable
        locators.append(Locator(fixed)) # final locator object
    # Next the formatter
    cformatter = Formatter(cformatter)

    # Fix the norm object
    # Check out the *insanely weird error* that occurs when you comment out this block!
    # * The error is triggered when a *major* tick sits exactly on vmin, but
    #   the actual error is due to processing of *minor* ticks, even if the 
    #   minor locator was set to NullLocator; very weird
    # * Happens when we call get_ticklabels(which='both') below. Can be prevented
    #   by just calling which='major'. Minor ticklabels are never drawn anyway.
    # * We can eliminate the normfix below, but that actually causes an annoying
    #   warning to be printed (related to same issue I guess). So we keep this.
    #   The culprit for all of this seems to be the colorbar API line:
    #        z = np.take(y, i0) + (xn - np.take(b, i0)) * dy / db
    # * Also strange that minorticks extending *below* the minimum
    #   don't raise the error. It is only when they are exaclty on the minimum.
    # * Note that when changing the levels attribute, need to make sure the
    #   levels datatype is float; otherwise division will be truncated and bottom
    #   level will still lie on same location, so error will occur
    if normfix:
        mappable.norm.vmin -= (mappable.norm.vmax-mappable.norm.vmin)/10000
    if hasattr(mappable.norm,'levels'):
        mappable.norm.levels = np.atleast_1d(mappable.norm.levels).astype(np.float)
        if normfix:
            mappable.norm.levels[0] -= np.diff(mappable.norm.levels[:2])[0]/10000

    # Draw the colorbar
    # TODO: For whatever reason the only way to avoid bugs seems to be to pass
    # the major formatter/locator to colorbar commmand and directly edit the
    # minor locators/formatters; update_ticks after the fact ignores the major formatter
    # axis.set_major_locator(locators[0]) # does absolutely nothing
    # axis.set_major_formatter(cformatter)
    if orientation=='horizontal':
        axis = ax.xaxis
        scale = ax.figure.width*np.diff(getattr(ax.get_position(),'intervalx'))[0]
    else:
        axis = ax.yaxis
        scale = ax.figure.height*np.diff(getattr(ax.get_position(),'intervaly'))[0]
    extendlength = extendlength/(scale - 2*extendlength)
    csettings.update({'extendfrac':extendlength}) # width of colorbar axes and stuff
    # cb = ax.figure.colorbar(mappable, **csettings)
    cb = ax.figure.colorbar(mappable,
            ticklocation=ticklocation,
            ticks=locators[0],
            format=cformatter,
            **csettings)

    # Make edges/dividers consistent with axis edges
    if cb.dividers is not None:
        cb.dividers.update(rc['grid'])

    # The minor locators and formatters
    # * The minor locator must be set with set_ticks after transforming an array
    #   using the mappable norm object; see: https://stackoverflow.com/a/20079644/4970632
    # * The set_minor_locator seems to be completely ignored depending on the colorbar
    #   in question, for whatever reason
    # * The major locator and formatter settings here are also not ideal since we'd have to
    #   update_ticks which might throw off the minor ticks again
    # WARNING: If functionality of BoundaryNorm is modified so data is transformed
    # by some linear transformation before getting binned, below may fail.
    # cb.minorticks_on() # alternative, but can't control the god damn spacing/set our own version
    # axis.set_minor_locator(locators[1]) # does absolutely nothing
    # WARNING: For some reason, pcolor mappables need to take *un-normalized
    # ticks* when set_ticks is called, while contourf mappables need to
    # take *normalized* data (verify by printing)
    minorvals = np.array(locators[1].tick_values(mappable.norm.vmin, mappable.norm.vmax))
    # axis.set_ticks(mappable.norm(majorvals), minor=False)
    if isinstance(mappable.norm, mcolors.BoundaryNorm): # including my own version
        vmin, vmax = mappable.norm.vmin, mappable.norm.vmax
        minorvals = (minorvals-vmin)/(vmax-vmin)
    elif hasattr(mappable, 'levels'):
        minorvals = mappable.norm(minorvals)
    axis.set_ticks(minorvals, minor=True)
    axis.set_minor_formatter(mticker.NullFormatter()) # to make sure
    # Set up the label
    if clabel is not None:
        axis.label.update({'text':clabel})
    # Fix alpha issues (cannot set edgecolor to 'face' if alpha non-zero
    # because blending will occur, will get colored lines instead of white ones;
    # need to perform manual alpha blending)
    # NOTE: For some reason cb solids uses listed colormap with always 1.0
    # alpha, then alpha is applied after.
    # See: https://stackoverflow.com/a/35672224/4970632
    alpha = cb.solids.get_alpha()
    if alpha is not None and alpha<1:
        # First get reference color
        print('Performing manual alpha-blending for colorbar solids.')
        reference = mappable.axes.get_facecolor() # the axes facecolor
        reference = [(1 - reference[-1]) + reference[-1]*color for color in reference[:3]]
        # Next get solids
        reference = [1,1,1] # override?
        alpha = 1 - (1 - alpha)**2 # make more colorful
        colors = cb.solids.get_cmap().colors
        colors = np.array(colors)
        for i in range(3): # Do not include the last column!
            colors[:,i] = (reference[i] - alpha) + alpha*colors[:,i]
        cmap = mcolors.ListedColormap(colors, name='colorbar-fix')
        cb.solids.set_cmap(cmap)
        cb.solids.set_alpha(1.0)
        # cb.solids.set_cmap()
    # Fix pesky white lines between levels + misalignment with border due to rasterized blocks
    cb.solids.set_linewidth(0.2) # something small
    cb.solids.set_edgecolor('face')
    cb.solids.set_rasterized(False)
    return cb

