#!/usr/bin/env python
"""
Parallel XRD Database Builder for Cluster Computing
====================================================

This script builds the XRD database using multiprocessing for faster processing
on multi-core systems or computing clusters.

Usage:
    python build_database_parallel.py --workers 32 --batch-size 1000

Arguments:
    --db-path: Path to input crystal structure database (default: UniqCryLabeled.db)
    --output: Path to output XRD database (default: xrd_database.pkl)
    --workers: Number of parallel workers (default: all CPU cores)
    --batch-size: Batch size for processing (default: 5000)
    --save-interval: Save checkpoint every N entries (default: 1000)
    --max-entries: Maximum entries to process (default: None = all)
    --wavelength: X-ray wavelength (default: CuKa)
    --n-peaks: Number of peaks to extract (default: 30)
"""

import argparse
import time
import logging
from pathlib import Path
from multiprocessing import cpu_count

from XMatcher.database import DatabaseBuilder

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('build_database.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Build XRD database with parallel processing'
    )
    
    parser.add_argument(
        '--db-path',
        type=str,
        default='UniqCryLabeled.db',
        help='Path to input crystal structure database'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='xrd_database.pkl',
        help='Path to output XRD database'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help=f'Number of parallel workers (default: {cpu_count()} = all cores)'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=5000,
        help='Batch size for processing (default: 5000)'
    )
    
    parser.add_argument(
        '--save-interval',
        type=int,
        default=1000,
        help='Save checkpoint every N entries (default: 1000)'
    )
    
    parser.add_argument(
        '--max-entries',
        type=int,
        default=None,
        help='Maximum entries to process (default: None = all)'
    )
    
    parser.add_argument(
        '--wavelength',
        type=str,
        default='CuKa',
        help='X-ray wavelength (default: CuKa)'
    )
    
    parser.add_argument(
        '--n-peaks',
        type=int,
        default=30,
        help='Number of peaks to extract per structure (default: 30)'
    )
    
    parser.add_argument(
        '--two-theta-min',
        type=float,
        default=10.0,
        help='Minimum 2θ angle (default: 10.0)'
    )
    
    parser.add_argument(
        '--two-theta-max',
        type=float,
        default=90.0,
        help='Maximum 2θ angle (default: 90.0)'
    )

    parser.add_argument(
        '--save-json',
        action='store_true',
        help='Also save database as JSON (not recommended for large databases)'
    )

    return parser.parse_args()


def main():
    """Main function."""
    args = parse_args()
    
    # Display configuration
    logger.info("=" * 80)
    logger.info("XRD Database Builder - Parallel Mode")
    logger.info("=" * 80)
    logger.info(f"Input database: {args.db_path}")
    logger.info(f"Output file: {args.output}")
    logger.info(f"Workers: {args.workers if args.workers else cpu_count()} (available: {cpu_count()})")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Save interval: {args.save_interval}")
    logger.info(f"Max entries: {args.max_entries if args.max_entries else 'ALL'}")
    logger.info(f"Wavelength: {args.wavelength}")
    logger.info(f"Number of peaks: {args.n_peaks}")
    logger.info(f"2θ range: ({args.two_theta_min}, {args.two_theta_max})")
    logger.info("=" * 80)
    
    # Check if input database exists
    if not Path(args.db_path).exists():
        logger.error(f"Input database not found: {args.db_path}")
        return 1
    
    # Initialize builder
    logger.info("Initializing database builder...")
    builder = DatabaseBuilder(
        db_path=args.db_path,
        wavelength=args.wavelength,
        n_peaks=args.n_peaks,
        two_theta_range=(args.two_theta_min, args.two_theta_max)
    )
    
    # Get total entries
    total_entries = builder.db_processor.get_total_entries()
    logger.info(f"Total entries in database: {total_entries}")
    
    if args.max_entries:
        logger.info(f"Will process: {min(args.max_entries, total_entries)} entries")
    else:
        logger.info(f"Will process: ALL {total_entries} entries")
    
    # Start timer
    start_time = time.time()
    
    # Build database with parallel processing
    logger.info("Starting parallel database build...")
    logger.info("=" * 80)
    
    try:
        database_package = builder.build_database_parallel(
            output_path=args.output,
            max_entries=args.max_entries,
            skip_errors=True,
            n_workers=args.workers,
            batch_size=args.batch_size,
            save_interval=args.save_interval,
            save_json=args.save_json
        )
        
        # End timer
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # Display results
        total_processed = len(database_package["xrd_database"])
        logger.info("=" * 80)
        logger.info("Database Build Complete!")
        logger.info("=" * 80)
        logger.info(f"Total entries processed: {total_processed}")
        logger.info(f"Output file: {args.output}")
        logger.info(f"File size: {Path(args.output).stat().st_size / (1024*1024):.2f} MB")
        logger.info(f"Time elapsed: {elapsed_time / 60:.1f} minutes ({elapsed_time / 3600:.2f} hours)")
        
        if total_processed > 0:
            logger.info(f"Average time per entry: {elapsed_time / total_processed:.2f} seconds")
            logger.info(f"Processing rate: {total_processed / elapsed_time:.1f} entries/second")
        
        logger.info("=" * 80)
        logger.info("SUCCESS!")
        
        return 0
        
    except Exception as e:
        logger.error(f"Database build failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    exit(main())
