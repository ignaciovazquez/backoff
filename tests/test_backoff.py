# coding:utf-8
import datetime
import pytest
import random
import threading

import backoff

from tests.common import _log_hdlrs, _save_target


def test_on_predicate(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    @backoff.on_predicate(backoff.expo)
    def return_true(log, n):
        val = (len(log) == n - 1)
        log.append(val)
        return val

    log = []
    ret = return_true(log, 3)
    assert ret is True
    assert 3 == len(log)


def test_on_predicate_max_tries(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    @backoff.on_predicate(backoff.expo, jitter=None, max_tries=3)
    def return_true(log, n):
        val = (len(log) == n)
        log.append(val)
        return val

    log = []
    ret = return_true(log, 10)
    assert ret is False
    assert 3 == len(log)


def test_on_predicate_max_time(monkeypatch):
    nows = [
        datetime.datetime(2018, 1, 1, 12, 0, 10, 5),
        datetime.datetime(2018, 1, 1, 12, 0, 9, 0),
        datetime.datetime(2018, 1, 1, 12, 0, 1, 0),
        datetime.datetime(2018, 1, 1, 12, 0, 0, 0),
    ]

    class Datetime:
        @staticmethod
        def now():
            return nows.pop()

    monkeypatch.setattr('time.sleep', lambda x: None)
    monkeypatch.setattr('datetime.datetime', Datetime)

    def giveup(details):
        assert details['tries'] == 3
        assert details['elapsed'] == 10.000005

    @backoff.on_predicate(backoff.expo, jitter=None, max_time=10,
                          on_giveup=giveup)
    def return_true(log, n):
        val = (len(log) == n)
        log.append(val)
        return val

    log = []
    ret = return_true(log, 10)
    assert ret is False
    assert len(log) == 3


def test_on_exception(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    @backoff.on_exception(backoff.expo, KeyError)
    def keyerror_then_true(log, n):
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log = []
    assert keyerror_then_true(log, 3) is True
    assert 3 == len(log)


def test_on_exception_tuple(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    @backoff.on_exception(backoff.expo, (KeyError, ValueError))
    def keyerror_valueerror_then_true(log):
        if len(log) == 2:
            return True
        if len(log) == 0:
            e = KeyError()
        if len(log) == 1:
            e = ValueError()
        log.append(e)
        raise e

    log = []
    assert keyerror_valueerror_then_true(log) is True
    assert 2 == len(log)
    assert isinstance(log[0], KeyError)
    assert isinstance(log[1], ValueError)


def test_on_exception_max_tries(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    @backoff.on_exception(backoff.expo, KeyError, jitter=None, max_tries=3)
    def keyerror_then_true(log, n, foo=None):
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log = []
    with pytest.raises(KeyError):
        keyerror_then_true(log, 10, foo="bar")

    assert 3 == len(log)


def test_on_exception_success_random_jitter(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_exception(backoff.expo,
                          Exception,
                          on_success=log_success,
                          on_backoff=log_backoff,
                          on_giveup=log_giveup,
                          jitter=backoff.random_jitter,
                          factor=0.5)
    @_save_target
    def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(log['backoff']) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log['success']) == 1
    assert len(log['backoff']) == 2
    assert len(log['giveup']) == 0

    for i in range(2):
        details = log['backoff'][i]
        assert details['wait'] >= 0.5 * 2 ** i


def test_on_exception_success_full_jitter(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_exception(backoff.expo,
                          Exception,
                          on_success=log_success,
                          on_backoff=log_backoff,
                          on_giveup=log_giveup,
                          jitter=backoff.full_jitter,
                          factor=0.5)
    @_save_target
    def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(log['backoff']) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log['success']) == 1
    assert len(log['backoff']) == 2
    assert len(log['giveup']) == 0

    for i in range(2):
        details = log['backoff'][i]
        assert details['wait'] <= 0.5 * 2 ** i


def test_on_exception_success():
    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_exception(backoff.constant,
                          Exception,
                          on_success=log_success,
                          on_backoff=log_backoff,
                          on_giveup=log_giveup,
                          jitter=lambda: 0,
                          interval=0)
    @_save_target
    def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(log['backoff']) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log['success']) == 1
    assert len(log['backoff']) == 2
    assert len(log['giveup']) == 0

    for i in range(2):
        details = log['backoff'][i]
        elapsed = details.pop('elapsed')
        assert isinstance(elapsed, float)
        assert details == {'args': (1, 2, 3),
                           'kwargs': {'foo': 1, 'bar': 2},
                           'target': succeeder._target,
                           'tries': i + 1,
                           'wait': 0}

    details = log['success'][0]
    elapsed = details.pop('elapsed')
    assert isinstance(elapsed, float)
    assert details == {'args': (1, 2, 3),
                       'kwargs': {'foo': 1, 'bar': 2},
                       'target': succeeder._target,
                       'tries': 3}


def test_on_exception_giveup():
    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_exception(backoff.constant,
                          ValueError,
                          on_success=log_success,
                          on_backoff=log_backoff,
                          on_giveup=log_giveup,
                          max_tries=3,
                          jitter=lambda: 0,
                          interval=0)
    @_save_target
    def exceptor(*args, **kwargs):
        raise ValueError("catch me")

    with pytest.raises(ValueError):
        exceptor(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice and giving up once
    assert len(log['success']) == 0
    assert len(log['backoff']) == 2
    assert len(log['giveup']) == 1

    details = log['giveup'][0]
    elapsed = details.pop('elapsed')
    assert isinstance(elapsed, float)
    assert details == {'args': (1, 2, 3),
                       'kwargs': {'foo': 1, 'bar': 2},
                       'target': exceptor._target,
                       'tries': 3}


def test_on_exception_giveup_predicate(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    def on_baz(e):
        return str(e) == "baz"

    vals = ["baz", "bar", "foo"]

    @backoff.on_exception(backoff.constant,
                          ValueError,
                          giveup=on_baz)
    def foo_bar_baz():
        raise ValueError(vals.pop())

    with pytest.raises(ValueError):
        foo_bar_baz()

    assert not vals


def test_on_predicate_success():
    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_predicate(backoff.constant,
                          on_success=log_success,
                          on_backoff=log_backoff,
                          on_giveup=log_giveup,
                          jitter=lambda: 0,
                          interval=0)
    @_save_target
    def success(*args, **kwargs):
        # succeed after we've backed off twice
        return len(log['backoff']) == 2

    success(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log['success']) == 1
    assert len(log['backoff']) == 2
    assert len(log['giveup']) == 0

    for i in range(2):
        details = log['backoff'][i]

        elapsed = details.pop('elapsed')
        assert isinstance(elapsed, float)
        assert details == {'args': (1, 2, 3),
                           'kwargs': {'foo': 1, 'bar': 2},
                           'target': success._target,
                           'tries': i + 1,
                           'value': False,
                           'wait': 0}

    details = log['success'][0]
    elapsed = details.pop('elapsed')
    assert isinstance(elapsed, float)
    assert details == {'args': (1, 2, 3),
                       'kwargs': {'foo': 1, 'bar': 2},
                       'target': success._target,
                       'tries': 3,
                       'value': True}


def test_on_predicate_giveup():
    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_predicate(backoff.constant,
                          on_success=log_success,
                          on_backoff=log_backoff,
                          on_giveup=log_giveup,
                          max_tries=3,
                          jitter=lambda: 0,
                          interval=0)
    @_save_target
    def emptiness(*args, **kwargs):
        pass

    emptiness(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice and giving up once
    assert len(log['success']) == 0
    assert len(log['backoff']) == 2
    assert len(log['giveup']) == 1

    details = log['giveup'][0]
    elapsed = details.pop('elapsed')
    assert isinstance(elapsed, float)
    assert details == {'args': (1, 2, 3),
                       'kwargs': {'foo': 1, 'bar': 2},
                       'target': emptiness._target,
                       'tries': 3,
                       'value': None}


def test_on_predicate_iterable_handlers():
    hdlrs = [_log_hdlrs() for _ in range(3)]

    @backoff.on_predicate(backoff.constant,
                          on_success=(h[1] for h in hdlrs),
                          on_backoff=(h[2] for h in hdlrs),
                          on_giveup=(h[3] for h in hdlrs),
                          max_tries=3,
                          jitter=lambda: 0,
                          interval=0)
    @_save_target
    def emptiness(*args, **kwargs):
        pass

    emptiness(1, 2, 3, foo=1, bar=2)

    for i in range(3):
        assert len(hdlrs[i][0]['success']) == 0
        assert len(hdlrs[i][0]['backoff']) == 2
        assert len(hdlrs[i][0]['giveup']) == 1

        details = dict(hdlrs[i][0]['giveup'][0])
        elapsed = details.pop('elapsed')
        assert isinstance(elapsed, float)
        assert details == {'args': (1, 2, 3),
                           'kwargs': {'foo': 1, 'bar': 2},
                           'target': emptiness._target,
                           'tries': 3,
                           'value': None}


# To maintain backward compatibility,
# on_predicate should support 0-argument jitter function.
def test_on_exception_success_0_arg_jitter(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)
    monkeypatch.setattr('random.random', lambda: 0)

    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_exception(backoff.constant,
                          Exception,
                          on_success=log_success,
                          on_backoff=log_backoff,
                          on_giveup=log_giveup,
                          jitter=random.random,
                          interval=0)
    @_save_target
    def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(log['backoff']) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log['success']) == 1
    assert len(log['backoff']) == 2
    assert len(log['giveup']) == 0

    for i in range(2):
        details = log['backoff'][i]
        elapsed = details.pop('elapsed')
        assert isinstance(elapsed, float)
        assert details == {'args': (1, 2, 3),
                           'kwargs': {'foo': 1, 'bar': 2},
                           'target': succeeder._target,
                           'tries': i + 1,
                           'wait': 0}

    details = log['success'][0]
    elapsed = details.pop('elapsed')
    assert isinstance(elapsed, float)
    assert details == {'args': (1, 2, 3),
                       'kwargs': {'foo': 1, 'bar': 2},
                       'target': succeeder._target,
                       'tries': 3}


# To maintain backward compatibility,
# on_predicate should support 0-argument jitter function.
def test_on_predicate_success_0_arg_jitter(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)
    monkeypatch.setattr('random.random', lambda: 0)

    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_predicate(backoff.constant,
                          on_success=log_success,
                          on_backoff=log_backoff,
                          on_giveup=log_giveup,
                          jitter=random.random,
                          interval=0)
    @_save_target
    def success(*args, **kwargs):
        # succeed after we've backed off twice
        return len(log['backoff']) == 2

    success(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log['success']) == 1
    assert len(log['backoff']) == 2
    assert len(log['giveup']) == 0

    for i in range(2):
        details = log['backoff'][i]
        elapsed = details.pop('elapsed')
        assert isinstance(elapsed, float)
        assert details == {'args': (1, 2, 3),
                           'kwargs': {'foo': 1, 'bar': 2},
                           'target': success._target,
                           'tries': i + 1,
                           'value': False,
                           'wait': 0}

    details = log['success'][0]
    elapsed = details.pop('elapsed')
    assert isinstance(elapsed, float)
    assert details == {'args': (1, 2, 3),
                       'kwargs': {'foo': 1, 'bar': 2},
                       'target': success._target,
                       'tries': 3,
                       'value': True}


def test_on_exception_callable_max_tries(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    def lookup_max_tries():
        return 3

    log = []

    @backoff.on_exception(backoff.constant,
                          ValueError,
                          max_tries=lookup_max_tries)
    def exceptor():
        log.append(True)
        raise ValueError()

    with pytest.raises(ValueError):
        exceptor()

    assert len(log) == 3


def test_on_exception_callable_gen_kwargs():

    def lookup_foo():
        return "foo"

    def wait_gen(foo=None, bar=None):
        assert foo == "foo"
        assert bar == "bar"

        while True:
            yield 0

    @backoff.on_exception(wait_gen,
                          ValueError,
                          max_tries=2,
                          foo=lookup_foo,
                          bar="bar")
    def exceptor():
        raise ValueError("aah")

    with pytest.raises(ValueError):
        exceptor()


def test_on_predicate_in_thread(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    result = []

    def check():
        try:
            @backoff.on_predicate(backoff.expo)
            def return_true(log, n):
                val = (len(log) == n - 1)
                log.append(val)
                return val

            log = []
            ret = return_true(log, 3)
            assert ret is True
            assert 3 == len(log)

        except Exception as ex:
            result.append(ex)
        else:
            result.append('success')

    t = threading.Thread(target=check)
    t.start()
    t.join()

    assert len(result) == 1
    assert result[0] == 'success'


def test_on_exception_in_thread(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)

    result = []

    def check():
        try:
            @backoff.on_exception(backoff.expo, KeyError)
            def keyerror_then_true(log, n):
                if len(log) == n:
                    return True
                e = KeyError()
                log.append(e)
                raise e

            log = []
            assert keyerror_then_true(log, 3) is True
            assert 3 == len(log)

        except Exception as ex:
            result.append(ex)
        else:
            result.append('success')

    t = threading.Thread(target=check)
    t.start()
    t.join()

    assert len(result) == 1
    assert result[0] == 'success'
