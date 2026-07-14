package ca.inn.bundler.model;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;


public class BundleStatusTest {
    @Test
    void pendingCanTransitionToProcessingOrFailed(){
        assertTrue(BundleStatus.PENDING.canTransitionTo(BundleStatus.PROCESSING));
        assertTrue(BundleStatus.PENDING.canTransitionTo(BundleStatus.FAILED));
    }

    @Test
    void processingCanTransitionToCompleteOrFailed(){
        assertTrue(BundleStatus.PROCESSING.canTransitionTo(BundleStatus.COMPLETE));
        assertTrue(BundleStatus.PROCESSING.canTransitionTo(BundleStatus.FAILED));
    }


    @Test
    void completeCannotTransitionToAnyStatus(){
        assertFalse(BundleStatus.COMPLETE.canTransitionTo(BundleStatus.PENDING));
        assertFalse(BundleStatus.COMPLETE.canTransitionTo(BundleStatus.PROCESSING));
        assertFalse(BundleStatus.COMPLETE.canTransitionTo(BundleStatus.FAILED));
    }

    @Test
    void failedCannotTransitionToAnyStatus(){
        assertFalse(BundleStatus.FAILED.canTransitionTo(BundleStatus.PENDING));
        assertFalse(BundleStatus.FAILED.canTransitionTo(BundleStatus.PROCESSING));

        assertFalse(BundleStatus.FAILED.canTransitionTo(BundleStatus.COMPLETE));

    }
}
