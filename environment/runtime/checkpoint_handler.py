"""Checkpoint Handler — determines the WAL replay boundary from checkpoint records."""


def find_last_checkpoint(records):
    """Scan all records to find the most recent checkpoint and return its LSN.

    The checkpoint record stores the checkpoint LSN in the after_image field.
    Returns the integer LSN of the last checkpoint found.
    """
    checkpoint_lsn = 0

    for record in records:
        if record["record_type"] == "checkpoint":
            lsn = int(record["after_image"])
            if lsn > checkpoint_lsn:
                checkpoint_lsn = lsn

    return checkpoint_lsn


def filter_records_after_checkpoint(records, checkpoint_lsn):
    """Return only records that need to be replayed after the checkpoint.

    Records at or after the checkpoint boundary are candidates for replay
    since they may not have been flushed to stable storage.
    """
    replay_records = []
    for record in records:
        # Include records from the checkpoint boundary onward
        if int(record["lsn"]) >= checkpoint_lsn:
            replay_records.append(record)

    return replay_records
