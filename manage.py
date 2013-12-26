#!/usr/bin/env python

from mkfacturi import create_app, create_manager


def main():
    app = create_app()
    manager = create_manager(app)
    manager.run()


if __name__ == '__main__':
    main()
