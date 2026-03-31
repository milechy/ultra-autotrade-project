.PHONY: cython-build cython-clean

cython-build:
	cd backend && python setup_cython.py build_ext --inplace

cython-clean:
	find backend/app/ai -name "*.so" -delete
	find backend/app/ai -name "*.c" -delete
	rm -rf backend/build/
