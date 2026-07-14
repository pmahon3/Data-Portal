package ca.inn.bundler.exception;

public class BundleQueueFullException extends RuntimeException {
    public BundleQueueFullException() {
        super("Bundle worker queue is full");
    }
}
