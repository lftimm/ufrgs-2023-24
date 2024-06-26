from typing import Optional, Dict, Tuple, List
import math
import numpy as np
import scipy as sp


class SoilSpace:
    """
        SoilSpace Class:
            It represents the entire space of the problem.
            - The physical characteristics of the slope
            - The mechnanical characteristics of the soil
        Uses:
            Used standalone to define the soil before sending it to Model and Soil_fs
            Default values present to simplify analysing behaviour
    """

    def __init__(self, c=20, phi=30, gam=18.5, alp=45, h=15, num_slice=50, circle: Dict[str, float] = None):
        self.properties = {
            'c': c,
            'phi': math.radians(phi),
            'gam': gam,
            'alp': math.radians(alp),
            'h': h,
            'num_slice': num_slice
        }

        self.update_slope_len()
        self.update_circle(self, circle)

    def update_slope_len(self):
        self.properties['slope_len'] = self.properties['h'] / math.tan(self.properties['alp'])

    @staticmethod
    def update_circle(self, circle):
        if not circle:
            xc = 0.5 * self.properties['h'] / math.tan(self.properties['alp'])
            yc = 1.333 * self.properties['h']
            r = 1 * math.sqrt(xc ** 2 + yc ** 2)
        else:
            keys = list(circle.keys())
            assert ('xc' in keys and 'yc' in keys and 'R' in keys), f'Invalid keys {keys}'
            xc = circle['xc']
            yc = circle['yc']
            r = circle['R']

        circle = {
            'xc': xc,
            'yc': yc,
            'R': r
        }

        print(circle)
        self.properties['Circle'] = circle

    def __str__(self):
        return f'{self.properties}'


class Model:
    """
    Model class:
    Responsible for calculating the factor of safety of the slope.
    """

    def __init__(self, sl: Optional[SoilSpace] = None):
        if sl is None:
            sl = SoilSpace()

        self.soil = sl
        self.sl: Dict[str, float] = sl.properties

        self.circle: Dict[str, float] = self.sl['Circle']

        self.points: Tuple[Tuple, Tuple] = self.intersec()
        self.c_points: List[Tuple] = self.split_geometry()
        self.polys: List[np.array] = self.mk_polys()

        self.dxs, self.alphas = self.calc_alphas()
        self.polys_A: List[float] = self.calc_areas()

    def intersec(self) -> Tuple[Tuple, Tuple]:
        """
            Calculates the points of intersection of the slope and the circle.
            It uses second degree equations to find the intersections.
            It returns the points in order from left to right.
        """
        t = math.tan(self.sl['alp'])
        h = self.sl['h']
        l = self.sl['slope_len']
        r, xc, yc = self.circle['R'], self.circle['xc'], self.circle['yc']

        a = 1 + t ** 2
        b1 = -2 * xc
        b = b1 - 2 * t * yc
        c = xc ** 2 + yc ** 2 - r ** 2

        delta = b ** 2 - 4 * a * c

        assert delta > 0, f'Math error, delta:{delta} <= 0, Circle doesn\'t intersect slope.'

        def f(x):
            if 0 < x < l:
                return x, t * x
            elif x < 0:
                return xc - math.sqrt(r ** 2 - yc ** 2), 0
            else:
                return xc + math.sqrt(r ** 2 + 2 * h * yc - h ** 2 - yc ** 2), h

        x1 = (-b + math.sqrt(delta)) / (2 * a)
        x2 = (-b - math.sqrt(delta)) / (2 * a)

        p1 = f(x1)
        p2 = f(x2)

        p_l = p1 if p1[0] == min(p1[0], p2[0]) else p2
        p_r = p2 if p_l[0] == p1[0] else p1

        return p_l, p_r

    def split_geometry(self) -> List[Tuple]:
        """
            It splits the circle into equal parts based on the number of slices given.
            Together there is the total_angle method, it measures the total angle of the intersection points.
            It returns a list of tuples containing the points.
            One thing might be removed, in the definition of f() there is a rounding done with the map() function.
        """
        # a = math.tan(self.sl['alp'])
        p_l, p_r = self.points
        r, xc, yc = self.circle['R'], self.circle['xc'], self.circle['yc']
        ns = self.sl['num_slice']

        v_p_r = np.array(p_r)
        v_c = np.array([xc, yc])

        def total_angle(p1, p2, xc, yc):
            dist = lambda p1, p2: math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
            ct = (xc, yc)
            a, b, c = dist(p1, p2), dist(p1, ct), dist(p2, ct)
            tot_angle = math.acos(-(a ** 2 - (b ** 2 + c ** 2)) / (2 * b * c))

            return tot_angle

        tot_a = total_angle(p_l, p_r, xc, yc)
        alp = tot_a / ns
        gam = math.atan(abs((v_c[1] - v_p_r[1]) / (v_c[0] - v_p_r[0])))

        f = lambda n: map(lambda x: round(x, 2),
                          r * np.array([math.cos(-(gam + n * alp)), math.sin(-(gam + n * alp))]) + v_c)
        return [tuple(f(n)) for n in range(ns + 1)]

    def mk_polys(self) -> List[Tuple]:
        """
            This method creates the polygons whose areas are going to be calculated.
            It takes the list of points in the circle, reflects them into the corresponding part of the surface.
            Together with it there is the pair_points method, which takes the previous points and orders them counter-clockwise.
            It returns an array of 4x1 arrays with the points .
        """
        c_parts = self.c_points
        pts_x, pts_y = zip(*c_parts)
        a = self.sl['alp']
        h = self.sl['h']
        l = self.sl['slope_len']

        def f(x):
            if 0 <= x <= l:
                return round(a * x, 2)
            elif x > l:
                return h
            else:
                return 0

        up_c_parts = [(x, f(x)) for x in pts_x]

        full_points = [c_parts, up_c_parts]

        def pair_points(points):
            polys = []
            for i in range(0, len(points[0])):
                try:
                    polys.append([points[0][i], points[1][i], points[1][i + 1], points[0][i + 1]])
                except IndexError:
                    pass

            return np.array(polys)

        return pair_points(full_points)

    def calc_alphas(self):
        """
            Alpha angle of each slice of the circle (each polygon).
            Utilizes the arctan(x).
        """

        polys = self.polys
        alp = lambda dy, dx: math.atan(dy / dx)
        n_polys = polys.shape[0]

        # Potential performance lost
        alphas = []
        dxs = []
        for i in range(n_polys):
            dy = polys[i][0][1] - polys[i][-1][1]
            dx = polys[i][0][0] - polys[i][-1][0]

            dxs.append(dx)
            alphas.append(alp(dy, dx))

        return dxs, alphas

    def calc_areas(self) -> List[float]:
        """
            It calculates the areas of the polygons.
            It uses the shoelace formula for calculating the area.
            It returns an array containing the areas of each of the polygons.
        """
        p = self.polys

        areas = []

        for poly in p:
            n = len(poly)
            a = 0
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                a += (x1 * y2 - x2 * y1) / 2
            areas.append(a)

        return areas


class SoilFs:
    """
        SoilFs:
        Serves as a wrapper for everything.
        Houses methods for showing and analyzing data.
    """

    def __init__(self, soil: Optional[SoilSpace] = None):
        if not soil:
            soil = SoilSpace()

        self.soil = soil
        self.sl = soil.properties
        self.results = self.end_results()
        self.fs = {'Fellenius': self.results.fun
        }

    def end_results(self) -> Tuple[float]:
        """
            Finalizes everything by gathering all the previous steps and calculating the FS.
            Bishop is an implicit equation, its roots are found using Newton's method (via Scipy.optimize)
            It returns both values in a dictionary format, according to the format used by the SoilSpace class.
        """
        c0 = list(self.sl['Circle'].values())
        model_0 = Model(self.soil)
        fs = self.fellenius(model_0)
        print(f"Inicial {fs}")

        return (
            sp.optimize.minimize(self.fellenius_call, x0=c0,method='SLSQP')
        )

    def fellenius_call(self, c0: List[float]):
        circle = {
            'xc': c0[0],
            'yc': c0[1],
            'R': c0[2]
        }
        print(c0)
        self.soil.update_circle(self.soil, circle)
        model = Model(self.soil)

        return self.fellenius(model)

    def bishop_call(self, c0):
        circle = {
            'xc': c0[0],
            'yc': c0[1],
            'R': c0[2]
        }
        print(c0)
        self.soil.update_circle(self.soil, circle)
        model = Model(self.soil)

        return self.bishop(model)

    @staticmethod
    def fellenius(model: Model, u=0):
        c = model.sl['c']
        slen = model.sl['slope_len']
        gam = model.sl['gam']
        phi = model.sl['phi']
        n = model.sl['num_slice']
        are = model.polys_A
        alp = model.alphas
        size = len(are)

        fell1 = sum(
            [c * slen / n + (gam * are[i] * math.cos(alp[i]) - u * slen) * math.tan(phi) for i in range(size)])
        fell2 = sum([gam * are[i] * math.sin(alp[i]) for i in range(size)])

        fs = fell1 / fell2
        return fs

    @staticmethod
    def bishop(model):
        c = model.sl['c']
        gam = model.sl['gam']
        phi = model.sl['phi']
        are = model.polys_A
        alp = model.alphas
        dxs = model.dxs
        size = len(are)

        def bishop_calc(fs):
            bip1 = (sum([gam * are[i] * math.sin(alp[i]) for i in range(size)])) ** -1
            bip2 = sum([(c * dxs[i] + gam * are[i] * math.tan(phi)) / (
                    math.cos(alp[i]) + math.sin(alp[i]) * math.tan(phi) / fs) for i in range(size)])
            return fs - bip1 * bip2

        return sp.optimize.newton(bishop_calc, x0=2)

    def __str__(self):
        return f'{self.fs}'


def main():
    soil = SoilSpace()
    fs = SoilFs(soil)
    print(fs.results)

if __name__ == '__main__':
    main()