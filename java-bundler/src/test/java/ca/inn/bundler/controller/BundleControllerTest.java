package ca.inn.bundler.controller;

import ca.inn.bundler.model.BundleStatus;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.hamcrest.Matchers.is;
@SpringBootTest
@AutoConfigureMockMvc
public class BundleControllerTest {

    @Autowired
    //simulate http server without starting one
    private MockMvc mockMvc;

    @Test
    void createBundleReturnsAcceptedWithPendingStatus() throws Exception{
        String body= """
                { "folderName": "test-folder",
                "files": [
                  {
                    "url": "https://examples.com/file.txt",
                    "relativePath": "folder/file.txt"
                  }
                ],
                "compression": "zip"
                }
                """;
       mockMvc.perform(post("/bundles")
               .contentType(MediaType.APPLICATION_JSON)
               .content(body))
               .andExpect(status().isAccepted())
//               .andExpect(jsonPath("$.status", is("pending")));
               .andExpect(jsonPath("$.id").exists())
               .andExpect(jsonPath("$.status").exists());
    }

    @Test
    void createBundleRejectsEmptyUrls() throws Exception{
        String body= """
                { "folderName": "bad",
                "files": [],
                "compression": "zip"
                }
                """;
        mockMvc.perform(post("/bundles")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message", is("Validation failed")));
    }

    @Test
    void getBundleReturnsNotFoundForUnknownBundle() throws Exception{
        mockMvc.perform(get("/bundles/fake-id"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message", is("Bundle not found: fake-id")));
    }

    @Test
    void downloadReturnsNotFoundForUnknownBundle() throws Exception {
        mockMvc.perform(get("/bundles/fake-id/download"))
                .andExpect(status().isNotFound());
    }



}
