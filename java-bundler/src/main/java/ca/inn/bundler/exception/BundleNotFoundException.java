package ca.inn.bundler.exception;

public class BundleNotFoundException extends RuntimeException {
    public BundleNotFoundException(String bundleId) {
        super("Bundle not found: " + bundleId);
    }
}
