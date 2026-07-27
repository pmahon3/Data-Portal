package ca.inn.bundler.controller;

import ca.inn.bundler.exception.BundleQueueFullException;
import ca.inn.bundler.service.BundleService;
import org.springframework.http.MediaType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

// This starts a small Spring MVC test context. It does not load the full app
@WebMvcTest(BundleController.class)
public class BundleControllerQueueFullTest {
    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private BundleService bundleService;

    @Test
    void createBundleReturnsServiceUnavailableWhenQueueIsFull() throws Exception {
        //Mockito setup. When createbundle with mock service with any argument, throw queue is full exception
        when(bundleService.createBundle(any()))
                .thenThrow(new BundleQueueFullException());

        String body = """
                {
                    "folderName": "test-folder",
                    "files": [
                        {
                            "url": "https://example.com/file.txt",
                            "relativePath": "folder/file.txt"
                        }
                    ],
                    "compression": "zip"
                }
                """;
        mockMvc.perform(post("/bundles")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status", is(503)))
                .andExpect(jsonPath("$.message", is("Bundle worker queue is full")));

    }
}
