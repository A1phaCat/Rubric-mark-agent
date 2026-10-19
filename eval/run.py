"""Golden-set runner skeleton. Private datasets belong in eval/datasets/ and are ignored."""

from pathlib import Path


def main() -> None:
    datasets = Path(__file__).with_name("datasets")
    if not any(datasets.glob("*.json")):
        print("No private golden-set datasets found; evaluation skeleton is ready.")
        return
    raise NotImplementedError("TODO(eval): implement DEV-GUIDE §G16 golden-set runner")


if __name__ == "__main__":
    main()

