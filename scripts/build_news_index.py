from ml.retrieval import build_index, build_parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    build_index(args.dataset, args.output, args.model, args.batch_size)
