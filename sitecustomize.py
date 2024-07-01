import coverage

cov = coverage.process_startup()

if cov is not None:
    import atexit

    def stop():
        cov.stop()
        cov.save()

    atexit.register(stop)
