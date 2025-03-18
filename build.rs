use glob::glob;
use proc_macro2::TokenStream;
use quote::{quote, ToTokens};
use std::{env, error::Error, fs, path::Path};
use syn::{parse_file, Ident, Item, Type};

fn main() -> Result<(), Box<dyn Error>> {
    let pattern = "src/features/*.rs";
    let mut field_tokens: Vec<TokenStream> = Vec::new();

    for entry in glob(pattern)? {
        let path = entry?;
        let content = fs::read_to_string(&path)?;
        let syntax = parse_file(&content)?;

        let module_name = path.file_stem().unwrap().to_str().unwrap();
        let mod_ident = Ident::new(module_name, proc_macro2::Span::call_site());

        // Iterate over the top-level items in the file.
        for item in syntax.items {
            if let Item::Struct(item_struct) = item {
                // Look for a `#[derive(..., ClusterFeatureValues, ...)]` attribute.
                let mut has_marker = false;
                for attr in &item_struct.attrs {
                    if attr.path().is_ident("derive") {
                        let _ = attr.parse_nested_meta(|meta| {
                            if meta.path.is_ident("ClusterFeatureValues") {
                                has_marker = true;
                            }
                            Ok(())
                        });
                    }
                }
                if !has_marker {
                    continue;
                }

                // This struct is marked with ClusterFeatureValues.
                // We assume its fields are named.
                if let syn::Fields::Named(fields_named) = &item_struct.fields {
                    for field in fields_named.named.iter() {
                        if let Some(ident) = &field.ident {
                            // Preserve all attributes for the field (like #[serde(rename = "...")])
                            let attrs = &field.attrs;
                            let ty = &field.ty;

                            let qualified_ty = match &field.ty {
                                Type::Path(type_path) => {
                                    let type_name =
                                        type_path.clone().into_token_stream().to_string();
                                    if type_name == "String"
                                        || type_name == "i64"
                                        || type_name == "bool"
                                        || type_name == "Vec < String >"
                                    {
                                        quote! { #ty }
                                    } else {
                                        println!(
                                            "cargo-warning: {} is not a primitive type",
                                            type_name
                                        );
                                        quote! { crate::features::#mod_ident::#ty }
                                    }
                                }
                                _ => quote! { #field.ty },
                            };

                            let tokens = quote! {
                                #(#attrs)*
                                pub #ident: #qualified_ty,
                            };
                            field_tokens.push(tokens);
                        }
                    }
                }
            }
        }
    }

    let output = quote! {
        use serde::{Serialize, Deserialize};
        use typed_builder::TypedBuilder;

        #[derive(Clone, Serialize, Deserialize, TypedBuilder)]
        pub struct Values {
            #(#field_tokens)*
        }
    };

    let out_dir = env::var("OUT_DIR")?;
    let dest_path = Path::new(&out_dir).join("values.rs");
    fs::write(&dest_path, output.to_string())?;

    println!("cargo:rerun-if-changed=src/features/");
    Ok(())
}
