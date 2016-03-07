from datetime import datetime, timedelta
import shutil
import string
import sys
import time

try:
    import pkg_resources
except ImportError:
    pass
else:
    VERSION = pkg_resources.get_distribution(__package__).version


class Formatter(string.Formatter):
    """
    Allow to have some custom formatting types.
    """

    def format_bytes(self, size, spec=None):
        SUFFIXES = ['KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
        spec = spec or '.1'
        for suffix in SUFFIXES:
            size /= 1024
            if size < 1024:
                return '{value:{spec}f} {suffix}'.format(value=size, spec=spec,
                                                         suffix=suffix)

    def format_field(self, value, format_string):
        if format_string.endswith("B"):
            spec = format_string[:-1]
            return self.format_bytes(int(value), spec=spec)
        else:
            return super().format_field(value, format_string)


class ProgressBar:

    prefix = 'Progress:'
    done_char = '='
    remain_char = ' '
    template = '{prefix} {animation} {percent} ({done}/{total})'
    done = 0
    total = 0
    start = None
    steps = ('-', '\\', '|', '/')
    animation = '{progress}'
    invisible_chars = 1  # "\r"
    supply = 0
    outro = '\n'
    throttle = 0  # Do not render unless done step is more than throttle.

    def __init__(self, **kwargs):
        self.columns = self.compute_columns()
        self.__dict__.update(kwargs)
        if not self.template.startswith('\r'):
            self.template = '\r' + self.template
        self.formatter = Formatter()
        self._last_render = 0

    def format(self, tpl, *args, **kwargs):
        return self.formatter.vformat(tpl, None, self)

    def compute_columns(self):
        return shutil.get_terminal_size((80, 20)).columns

    def keys(self):
        return [k for k in dir(self) if not k.startswith('_')]

    def __getitem__(self, item):
        return getattr(self, item, '')

    @property
    def spinner(self):
        step = self.done % len(self.steps)
        return self.steps[int(step)]

    @property
    def progress(self):
        if not self.free_space:
            return ''
        done_chars = int(self.fraction * self.free_space)
        remain_chars = self.free_space - done_chars
        return self.done_char * done_chars + self.remain_char * remain_chars

    @property
    def stream(self):
        chars = []
        for i in range(self.free_space):
            idx = (self.done + i) % len(self.steps)
            chars.append(self.steps[idx])
        return ''.join(chars)

    @property
    def percent(self):
        return Percent(self.fraction)

    @property
    def eta(self):
        """Estimated time of arrival."""
        remaining_time = timedelta(seconds=self.tta)
        return ETA(datetime.now() + remaining_time)

    @property
    def speed(self):
        """Number of iterations per second."""
        return Float(1.0 / self.avg if self.avg else 0)

    def render(self):
        if self.done < self._last_render + self.throttle <= self.total:
            return
        self._last_render = self.done
        if self.start is None:
            self.start = time.time()
        self.free_space = 0
        self.remaining = self.total - self.done
        self.addition = self.done - self.supply
        self.fraction = min(self.done / self.total, 1.0) if self.total else 0
        self.elapsed = Timedelta(time.time() - self.start)
        self.avg = Float(self.elapsed / self.addition if self.addition else 0)
        self.tta = Timedelta(self.remaining * self.avg)

        line = self.format(self.template)

        self.free_space = (self.columns - len(line) + len(self.animation)
                           + self.invisible_chars)
        sys.stdout.write(self.format(line))

        if self.fraction >= 1.0:
            self.finish()
        else:
            sys.stdout.flush()

    def finish(self):
        sys.stdout.write(self.format(self.outro))

    def __call__(self, **kwargs):
        self.update(**kwargs)

    def update(self, step=1, **kwargs):
        if step:
            self.done += step
        # Allow to override any properties.
        self.__dict__.update(kwargs)
        if self.start is None and 'done' in kwargs:
            # First call to update and forcing a done value. May be
            # resuming a download. Keep track for better ETA computation.
            self.supply = self.done
        self.render()

    def __next__(self):
        self.update()

    def iter(self, iterable):
        for i in iterable:
            yield i
            self.update()
        if self.fraction != 1.0:
            # Spinner without total.
            self.finish()


# Manage sane default formats while keeping the original type to allow any
# built-in formatting syntax.

class Float(float):

    def __format__(self, format_spec):
        if not format_spec:
            format_spec = '.2f'
        return super().__format__(format_spec)


class Percent(float):

    def __format__(self, format_spec):
        if not format_spec:
            format_spec = '.2%'
        return super().__format__(format_spec)


class ETA(datetime):

    def __new__(cls, *args, **kwargs):
        if args and isinstance(args[0], datetime.datetime):
            # datetime + timedelta returns a datetime, while we want an ETA.
            dt = args[0]
            super().__new__(year=dt.year, month=dt.month, day=dt.day,
                            hour=dt.hour, minute=dt.minute, second=dt.second,
                            tzinfo=dt.tzinfo)
        else:
            super().__new__(*args, **kwargs)

    def __format__(self, format_spec):
        if not format_spec:
            now = datetime.now()
            diff = self - now
            format_spec = '%H:%M:%S'
            if diff.days > 1:
                format_spec = '%Y-%m-%d %H:%M:%S'
        return super().__format__(format_spec)


class Timedelta(int):
    """An integer that is formatted by default as timedelta."""

    def format_as_timedelta(self):
        """Format seconds as timedelta."""
        # Do we want this as a Formatter type also?
        tmp = timedelta(seconds=self)
        # Filter out microseconds from str format.
        # timedelta does not have a __format__ method, and we don't want to
        # recode it (we would need to handle i18n of "days").
        obj = timedelta(days=tmp.days, seconds=tmp.seconds)
        return str(obj)

    def __format__(self, format_spec):
        if not format_spec:
            return self.format_as_timedelta()
        return super().__format__(format_spec)