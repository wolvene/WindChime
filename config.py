import argparse
import os
from exceptions import ConfigurationError


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_PORT = 3306
DEFAULT_ATTEMPTS = 3
DEFAULT_LOG_FILE = os.path.join(BASE_DIR, "log", "windChime.log")
DEFAULT_SAVE_FOLDER = os.path.join(BASE_DIR, "Downloads")


class Config:

    def __init__(self):
        self.port = DEFAULT_PORT
        self.filename = None
        self.filelist = []
        self.attempts = DEFAULT_ATTEMPTS
        self.verbose = False
        self.debug = False

        self.log_file = DEFAULT_LOG_FILE
        self.save_folder = DEFAULT_SAVE_FOLDER

    @staticmethod
    def create_parser():
        parser = argparse.ArgumentParser(
            prog="WindChime",
            description="WindChime MySQL server"
        )

        parser.add_argument(
            "-p",
            metavar="port",
            type=int,
            default=DEFAULT_PORT,
            help="port to run the server on"
        )

        parser.add_argument(
            "-f",
            metavar="filename",
            help="specify a single filename"
        )

        parser.add_argument(
            "-l",
            metavar="filelist",
            help="path to file with list of files"
        )

        parser.add_argument(
            "-o",
            "--save-dir",
            metavar="directory",
            default=DEFAULT_SAVE_FOLDER,
            help="directory to save downloaded files"
        )

        parser.add_argument(
            "-a",
            metavar="attempts",
            type=int,
            default=DEFAULT_ATTEMPTS,
            help="how many times to retry a task"
        )

        parser.add_argument(
            "-v",
            action="store_true",
            help="toggle verbosity"
        )

        parser.add_argument(
            "-d",
            action="store_true",
            help="log debug messages"
        )

        return parser

    @classmethod
    def load(cls, argv=None):
        parser = cls.create_parser()
        args = parser.parse_args(argv)

        config = cls()

        config.port = args.p
        config.filename = args.f
        config.attempts = args.a
        config.verbose = args.v
        config.debug = args.d
        config.save_folder = os.path.abspath(args.save_dir)

        if not 1 <= config.port <= 65535:
            raise ConfigurationError("Invalid port number")

        if config.attempts < 1:
            raise ConfigurationError("Attempts must be greater than 0")

        if args.l:
            if not os.path.isfile(args.l):
                raise ConfigurationError(
                    "File list not found: {}".format(args.l)
                )

            try:
                with open(args.l, "r", encoding="utf-8") as file:
                    config.filelist = [
                        line.strip()
                        for line in file
                        if line.strip()
                    ]
            except OSError as exc:
                raise ConfigurationError(
                    "Unable to read file list: {}".format(exc)
                )

        elif config.filename:
            config.filelist = [config.filename]

        else:
            raise ConfigurationError(
                "No files specified. Use -f or -l."
            )

        if not config.filelist:
            raise ConfigurationError("File list is empty")

        return config

    def initialize(self):
        try:
            os.makedirs(
                self.save_folder,
                exist_ok=True
            )
        except OSError as exc:
            raise ConfigurationError(
                "Unable to create save directory: {}".format(exc)
            )
